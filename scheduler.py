"""
scheduler.py — Scheduled Harvesting Manager
Wraps APScheduler to allow date/time-based scheduling of all three
harvesting engines: Podcast, Document, and Web.
Jobs are persisted to schedules.json and survive server restarts.
"""

import os
import json
import uuid
import logging
import threading
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)

SCHEDULES_PATH = os.path.join(os.path.dirname(__file__), '.data', 'schedules.json')

# ── Singleton Scheduler Instance ──────────────────────────────────────────────
_scheduler = None
_scheduler_lock = threading.RLock()

# In-memory jobs registry (augments APScheduler with metadata)
_jobs_registry = {}
_registry_lock = threading.RLock()


def _load_registry():
    """Load persisted job registry from disk."""
    global _jobs_registry
    os.makedirs(os.path.dirname(SCHEDULES_PATH), exist_ok=True)
    if os.path.exists(SCHEDULES_PATH):
        try:
            with open(SCHEDULES_PATH, 'r') as f:
                _jobs_registry = json.load(f)
            # Sanitize any stuck running status to failed
            changed = False
            for job_id, job in list(_jobs_registry.items()):
                if job.get('status') == 'running':
                    trigger_type = job.get('trigger_type', 'once')
                    job['status'] = 'pending' if trigger_type in ('cron', 'interval') else 'failed'
                    job['error'] = 'Job execution interrupted by server restart.'
                    job['updated_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
                    
                    history_entry = {
                        'run_at': datetime.datetime.utcnow().isoformat() + 'Z',
                        'status': 'failed',
                        'logs': job.get('logs', []),
                        'error': 'Job execution interrupted by server restart.'
                    }
                    history_list = job.get('history', [])
                    if not isinstance(history_list, list):
                        history_list = []
                    history_list.append(history_entry)
                    job['history'] = history_list[-10:]
                    
                    changed = True
            if changed:
                _save_registry()
        except Exception as e:
            logger.warning(f"Failed to load schedules registry: {e}")
            _jobs_registry = {}
    else:
        _jobs_registry = {}


def _save_registry():
    """Persist the job registry to disk."""
    os.makedirs(os.path.dirname(SCHEDULES_PATH), exist_ok=True)
    try:
        with open(SCHEDULES_PATH, 'w') as f:
            json.dump(_jobs_registry, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save schedules registry: {e}")


def get_scheduler():
    """Return (and lazily initialise) the background scheduler."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            jobstores = {'default': MemoryJobStore()}
            executors = {'default': ThreadPoolExecutor(max_workers=2)}
            _scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                timezone='UTC'
            )
            _load_registry()
            _scheduler.start()
            logger.info("APScheduler started.")
            _reschedule_pending_jobs()
    return _scheduler


# ── Job Runners ───────────────────────────────────────────────────────────────

def _run_podcast_job(job_id, show_index, episode_index, config_path):
    """Execute a scheduled podcast sync."""
    _update_job_status(job_id, 'running')
    try:
        import json as _json
        from main import execute_sync_generator

        with open(config_path, 'r') as f:
            config = _json.load(f)

        logs = []
        for item in execute_sync_generator(show_index=show_index, episode_index=episode_index):
            try:
                data = _json.loads(item)
                if data.get('message'):
                    logs.append(data['message'])
            except Exception:
                pass

        _update_job_status(job_id, 'completed', logs=logs[-500:])
        logger.info(f"[Scheduled] Podcast job {job_id} completed.")
    except Exception as e:
        logger.error(f"[Scheduled] Podcast job {job_id} failed: {e}")
        _update_job_status(job_id, 'failed', error=str(e))


def _run_youtube_job(job_id, channel_index, video_index, config_path):
    """Execute a scheduled youtube sync."""
    _update_job_status(job_id, 'running')
    try:
        import json as _json
        from main import execute_youtube_sync_generator

        with open(config_path, 'r') as f:
            config = _json.load(f)

        logs = []
        for item in execute_youtube_sync_generator(channel_index=channel_index, video_index=video_index):
            try:
                data = _json.loads(item)
                if data.get('message'):
                    logs.append(data['message'])
            except Exception:
                pass

        _update_job_status(job_id, 'completed', logs=logs[-500:])
        logger.info(f"[Scheduled] YouTube job {job_id} completed.")
    except Exception as e:
        logger.error(f"[Scheduled] YouTube job {job_id} failed: {e}")
        _update_job_status(job_id, 'failed', error=str(e))

def _run_telegram_job(job_id, config_path, channel_index=None):
    """Execute a scheduled telegram harvest."""
    _update_job_status(job_id, 'running')
    try:
        import json as _json
        from telegram_harvester import TelegramHarvester
        with open(config_path, 'r') as f:
            config = _json.load(f)
            
        tg_config = config.get('telegram', {})
        api_id = tg_config.get('api_id')
        api_hash = tg_config.get('api_hash')
        phone = tg_config.get('phone')
        channels = tg_config.get('channels', [])
        limit = tg_config.get('limit', 100)
        
        if not api_id or not api_hash or not phone or not channels:
            raise ValueError("Telegram configuration is incomplete.")
            
        if channel_index is not None:
            if channel_index < 0 or channel_index >= len(channels):
                raise ValueError("Invalid channel index.")
            channels = [channels[channel_index]]
            
        if not channels:
             raise ValueError("No valid channels to scrape.")
            
        harvester = TelegramHarvester(api_id=api_id, api_hash=api_hash, phone=phone, download_dir=config.get('raw_material_path', './RawMaterials'))
        result = harvester.run_harvest(channels=channels, limit=limit)
        
        if result['status'] == 'error':
            raise Exception(result['error'])
            
        logs = [f"Downloaded {result['downloaded_files']} files."]
        _update_job_status(job_id, 'completed', logs=logs)
        logger.info(f"[Scheduled] Telegram job {job_id} completed.")
    except Exception as e:
        logger.error(f"[Scheduled] Telegram job {job_id} failed: {e}")
        _update_job_status(job_id, 'failed', error=str(e))



def _run_docs_job(job_id, target_files, config_path):
    """Execute a scheduled document harvest."""
    _update_job_status(job_id, 'running')
    try:
        import json as _json
        from doc_processor import process_documents_generator

        with open(config_path, 'r') as f:
            config = _json.load(f)

        raw_path = os.path.expanduser(config.get("raw_material_path", "./RawMaterials"))
        vault_path = os.path.expanduser(config.get("obsidian_vault_path", "./Vault"))
        gemini_key = config.get("api_keys", {}).get("gemini", "")
        gemini_model = config.get("gemini_model", "gemini-1.5-flash")
        engine = config.get("document_engine", "gemini")
        ollama_model = config.get("ollama_model", "")
        nuextract_model = config.get("nuextract_model", "numind/NuExtract3-mlx-4bits")
        restructure_prompt = config.get("restructure_prompt")
        chunk_size = config.get("chunk_size", 16000)
        chunk_overlap = config.get("chunk_overlap", 1000)
        archive_processed = config.get("archive_processed_docs", False)
        auto_restructure_ollama = config.get("auto_restructure_ollama", False)
        fidelity_min_ratio = config.get("fidelity_min_ratio", 0.5)

        logs = []
        for item in process_documents_generator(
            raw_path, vault_path, gemini_key, gemini_model,
            target_files=target_files, engine=engine, ollama_model=ollama_model,
            nuextract_model=nuextract_model,
            prompt_template=restructure_prompt, chunk_size=chunk_size, overlap=chunk_overlap,
            archive_processed=archive_processed, auto_restructure_ollama=auto_restructure_ollama,
            fidelity_min_ratio=fidelity_min_ratio
        ):
            try:
                data = _json.loads(item)
                if data.get('message'):
                    logs.append(data['message'])
            except Exception:
                pass

        _update_job_status(job_id, 'completed', logs=logs[-500:])
        logger.info(f"[Scheduled] Docs job {job_id} completed.")
    except Exception as e:
        logger.error(f"[Scheduled] Docs job {job_id} failed: {e}")
        _update_job_status(job_id, 'failed', error=str(e))


def _run_web_job(job_id, url, vault_path):
    """Execute a scheduled web harvest."""
    _update_job_status(job_id, 'running')
    try:
        import asyncio
        import json as _json
        from web_harvester import WebHarvester

        harvester = WebHarvester()
        logs = []

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _run():
            gen = harvester.harvest_hindu(url, vault_path)
            while True:
                try:
                    item = await gen.__anext__()
                    try:
                        data = _json.loads(item)
                        if data.get('message'):
                            logs.append(data['message'])
                    except Exception:
                        pass
                except StopAsyncIteration:
                    break

        loop.run_until_complete(_run())
        loop.close()

        _update_job_status(job_id, 'completed', logs=logs[-500:])
        logger.info(f"[Scheduled] Web job {job_id} completed.")
    except Exception as e:
        logger.error(f"[Scheduled] Web job {job_id} failed: {e}")
        _update_job_status(job_id, 'failed', error=str(e))


def _run_market_data_job(job_id, index):
    """Execute a scheduled market data harvest."""
    _update_job_status(job_id, 'running')
    try:
        from market_harvester import MarketHarvester
        harvester = MarketHarvester()
        
        if index is not None:
            success, message = harvester.harvest_single(index)
        else:
            success, message = harvester.harvest_all()
            
        if not success:
            raise Exception(message)
            
        logs = [message]
        _update_job_status(job_id, 'completed', logs=logs)
        logger.info(f"[Scheduled] Market Data job {job_id} completed.")
    except Exception as e:
        logger.error(f"[Scheduled] Market Data job {job_id} failed: {e}")
        _update_job_status(job_id, 'failed', error=str(e))


def _run_central_bank_job(job_id):
    """Execute a scheduled Central Bank & Macro Digest harvest."""
    _update_job_status(job_id, 'running')
    try:
        from central_bank_harvester import run_central_bank_harvest
        success, message = run_central_bank_harvest()
            
        if not success:
            raise Exception(message)
            
        logs = [message]
        _update_job_status(job_id, 'completed', logs=logs)
        logger.info(f"[Scheduled] Central Bank job {job_id} completed.")
    except Exception as e:
        logger.error(f"[Scheduled] Central Bank job {job_id} failed: {e}")
        _update_job_status(job_id, 'failed', error=str(e))

# ── Registry Helpers ──────────────────────────────────────────────────────────

def _update_job_status(job_id, status, logs=None, error=None):
    with _registry_lock:
        if job_id in _jobs_registry:
            job = _jobs_registry[job_id]
            trigger_type = job.get('trigger_type', 'once')

            if status in ('completed', 'failed'):
                job['last_run_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
                if logs is not None:
                    job['logs'] = logs
                if error is not None:
                    job['error'] = error
                
                # Append execution to history
                history_entry = {
                    'run_at': datetime.datetime.utcnow().isoformat() + 'Z',
                    'status': status,
                    'logs': logs or [],
                    'error': error
                }
                history_list = job.get('history', [])
                if not isinstance(history_list, list):
                    history_list = []
                history_list.append(history_entry)
                job['history'] = history_list[-10:]

                if trigger_type in ('cron', 'interval'):
                    job['status'] = 'pending'
                    scheduler = get_scheduler()
                    apsched_job = scheduler.get_job(job_id)
                    if apsched_job and apsched_job.next_run_time:
                        job['run_at'] = apsched_job.next_run_time.isoformat().replace('+00:00', 'Z')
                else:
                    job['status'] = status
            else:
                job['status'] = status
                if logs is not None:
                    job['logs'] = logs
                if error is not None:
                    job['error'] = error

            job['updated_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
            _save_registry()


def _reschedule_pending_jobs():
    """Re-register any pending jobs that were persisted before a restart."""
    now = datetime.datetime.utcnow()
    config_path = os.environ.get("CONFIG_PATH", os.path.join(os.path.dirname(__file__), 'config.json'))

    with _registry_lock:
        for job_id, job in list(_jobs_registry.items()):
            if job.get('status') != 'pending':
                continue

            trigger_type = job.get('trigger_type', 'once')
            run_at_naive = None

            if trigger_type == 'once':
                run_at_str = job.get('run_at')
                if not run_at_str:
                    continue
                try:
                    run_at = datetime.datetime.fromisoformat(run_at_str.replace('Z', '+00:00'))
                    run_at_naive = run_at.replace(tzinfo=None)
                except ValueError:
                    continue

                if run_at_naive <= now:
                    # Missed — mark as missed
                    job['status'] = 'missed'
                    continue

            engine = job.get('engine')
            payload = job.get('payload', {})

            start_date_naive = None
            created_at_str = job.get('created_at')
            if created_at_str:
                try:
                    dt = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    start_date_naive = dt.replace(tzinfo=None)
                except ValueError:
                    pass

            _schedule_apscheduler_job(
                job_id, engine, payload, run_at_naive, config_path,
                trigger_type=trigger_type,
                cron_hour=job.get('cron_hour'),
                cron_minute=job.get('cron_minute'),
                interval_value=job.get('interval_value'),
                interval_unit=job.get('interval_unit'),
                start_date=start_date_naive,
                scheduler=_scheduler
            )

            # Update next fire time in registry
            apsched_job = _scheduler.get_job(job_id)
            if apsched_job and apsched_job.next_run_time:
                job['run_at'] = apsched_job.next_run_time.isoformat().replace('+00:00', 'Z')

    _save_registry()


def _schedule_apscheduler_job(job_id, engine, payload, run_at_naive, config_path,
                              trigger_type='once', cron_hour=None, cron_minute=None,
                              interval_value=None, interval_unit=None, start_date=None, scheduler=None):
    """Register a job (one-time, cron, or interval) with APScheduler."""
    if scheduler is None:
        scheduler = get_scheduler()

    # Determine function and args based on engine
    if engine == 'podcast':
        func = _run_podcast_job
        args = [job_id, payload.get('show_index'), payload.get('episode_index'), config_path]
    elif engine == 'docs':
        func = _run_docs_job
        args = [job_id, payload.get('target_files'), config_path]
    elif engine == 'web':
        func = _run_web_job
        args = [job_id, payload.get('url'), payload.get('vault_path', './Vault')]
    elif engine == 'youtube':
        func = _run_youtube_job
        args = [job_id, payload.get('channel_index'), payload.get('video_index'), config_path]
    elif engine == 'telegram':
        func = _run_telegram_job
        args = [job_id, config_path, payload.get('channel_index')]
    elif engine == 'market_data':
        func = _run_market_data_job
        args = [job_id, payload.get('index')]
    elif engine == 'central_bank':
        func = _run_central_bank_job
        args = [job_id]
    else:
        logger.error(f"Unknown engine: {engine}")
        return

    # Set up trigger details
    if trigger_type == 'cron':
        trigger_args = {
            'trigger': 'cron',
            'hour': cron_hour,
            'minute': cron_minute,
            'timezone': 'UTC'
        }
    elif trigger_type == 'interval':
        unit = interval_unit if interval_unit in ('hours', 'minutes') else 'minutes'
        trigger_args = {
            'trigger': 'interval',
            **{unit: interval_value},
            'timezone': 'UTC'
        }
        if start_date:
            trigger_args['start_date'] = start_date
    else:  # 'once'
        trigger_args = {
            'trigger': 'date',
            'run_date': run_at_naive
        }

    scheduler.add_job(
        func,
        args=args,
        id=job_id,
        replace_existing=True,
        misfire_grace_time=3600,
        **trigger_args
    )


# ── Public API ────────────────────────────────────────────────────────────────

def add_schedule(engine, payload, run_at_iso, label, config_path,
                 trigger_type='once', cron_hour=None, cron_minute=None,
                 interval_value=None, interval_unit=None, job_id=None):
    """
    Schedule a harvesting job (supports once, daily cron, or interval).
    """
    get_scheduler()  # Ensure scheduler is running

    if not job_id:
        job_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.utcnow()
    run_at_naive = None

    if trigger_type == 'once':
        if not run_at_iso:
            raise ValueError("run_at_iso is required for 'once' schedule.")
        try:
            run_at = datetime.datetime.fromisoformat(run_at_iso.replace('Z', '+00:00'))
            run_at_naive = run_at.replace(tzinfo=None)
        except ValueError as e:
            raise ValueError(f"Invalid run_at format: {e}")

        if run_at_naive <= now:
            raise ValueError("Scheduled time must be in the future.")
    elif trigger_type == 'cron':
        if cron_hour is None or cron_minute is None:
            raise ValueError("cron_hour and cron_minute are required for 'cron' schedule.")
    elif trigger_type == 'interval':
        if not interval_value:
            raise ValueError("interval_value is required for 'interval' schedule.")

    job_record = {
        'id': job_id,
        'engine': engine,
        'label': label,
        'payload': payload,
        'run_at': run_at_iso,
        'trigger_type': trigger_type,
        'cron_hour': cron_hour,
        'cron_minute': cron_minute,
        'interval_value': interval_value,
        'interval_unit': interval_unit,
        'status': 'pending',
        'created_at': now.isoformat() + 'Z',
        'updated_at': now.isoformat() + 'Z',
        'logs': [],
        'error': None,
        'history': []
    }

    _schedule_apscheduler_job(
        job_id, engine, payload, run_at_naive, config_path,
        trigger_type=trigger_type,
        cron_hour=cron_hour,
        cron_minute=cron_minute,
        interval_value=interval_value,
        interval_unit=interval_unit,
        start_date=now
    )

    scheduler = get_scheduler()
    apsched_job = scheduler.get_job(job_id)
    if apsched_job and apsched_job.next_run_time:
        job_record['run_at'] = apsched_job.next_run_time.isoformat().replace('+00:00', 'Z')

    with _registry_lock:
        _jobs_registry[job_id] = job_record
        _save_registry()

    logger.info(f"[Scheduler] Scheduled {engine} job '{label}' (type={trigger_type}, id={job_id})")
    return job_id


def list_schedules():
    """Return all jobs sorted by run_at descending."""
    with _registry_lock:
        jobs = list(_jobs_registry.values())

    jobs.sort(key=lambda j: j.get('run_at', ''), reverse=True)
    return jobs


def cancel_schedule(job_id):
    """Cancel a pending scheduled job."""
    scheduler = get_scheduler()

    with _registry_lock:
        if job_id not in _jobs_registry:
            return False, "Job not found."

        job = _jobs_registry[job_id]
        if job['status'] not in ('pending', 'running'):
            return False, f"Cannot cancel a job with status '{job['status']}'."

        # Remove from APScheduler
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass  # Already fired or not found

        _jobs_registry[job_id]['status'] = 'cancelled'
        _jobs_registry[job_id]['updated_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
        _save_registry()

    return True, "Job cancelled."


def delete_schedule(job_id):
    """Delete a job entirely from the registry."""
    scheduler = get_scheduler()

    with _registry_lock:
        if job_id not in _jobs_registry:
            return False, "Job not found."

        job = _jobs_registry[job_id]
        if job['status'] == 'running':
            return False, "Cannot delete a running job. Cancel it first."

        if job['status'] == 'pending':
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

        del _jobs_registry[job_id]
        _save_registry()

    return True, "Job deleted."


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
