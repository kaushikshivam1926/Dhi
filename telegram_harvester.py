import os
import logging
import asyncio
from telethon import TelegramClient

logger = logging.getLogger(__name__)

class TelegramHarvester:
    def __init__(self, api_id, api_hash, phone, download_dir="RawMaterials"):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        
        # We need a unique session name
        self.session_name = os.path.join(os.path.dirname(__file__), ".data", "tg_session")
        os.makedirs(os.path.dirname(self.session_name), exist_ok=True)

    async def _fetch_channel_files(self, client, channel, limit, date_limit, file_types, keywords):
        logger.info(f"Fetching from {channel} (limit={limit}, file_types={file_types}, keywords={keywords})")
        downloaded = 0
        try:
            entity = await client.get_entity(channel)
            kwargs = {}
            if limit:
                kwargs['limit'] = limit
            else:
                kwargs['limit'] = 100 # default fallback
                
            # Prepare keywords list (lowercase for case-insensitive matching)
            kw_list = [k.strip().lower() for k in keywords.split(',')] if keywords else []
                
            async for message in client.iter_messages(entity, **kwargs):
                if message.document:
                    mime_type = message.document.mime_type
                    is_pdf = 'pdf' in mime_type.lower()
                    
                    if ('pdf' in file_types and is_pdf):
                        filename = None
                        for attr in message.document.attributes:
                            if hasattr(attr, 'file_name'):
                                filename = attr.file_name
                                break
                        
                        if not filename:
                            filename = f"telegram_{message.id}.pdf"
                            
                        # Suffix date of upload to the filename
                        if message.date:
                            date_str = message.date.strftime('%Y-%m-%d')
                            name, ext = os.path.splitext(filename)
                            filename = f"{name}_{date_str}{ext}"
                            
                        # Apply keyword filter if keywords are provided
                        if kw_list:
                            name_lower = filename.lower()
                            if not any(kw in name_lower for kw in kw_list if kw):
                                continue # Skip if no keywords match
                            
                        filepath = os.path.join(self.download_dir, filename)
                        if not os.path.exists(filepath):
                            logger.info(f"Downloading {filename}...")
                            await message.download_media(file=filepath)
                            downloaded += 1
                        else:
                            logger.info(f"File {filename} already exists, skipping.")
                            
        except Exception as e:
            logger.error(f"Failed to fetch from {channel}: {e}")
            raise e
        return downloaded

    def run_harvest(self, channels, limit=100, date_limit=None, file_types=None):
        if file_types is None:
            file_types = ['pdf']
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        
        try:
            client.start(phone=self.phone)
            
            total_downloaded = 0
            for ch in channels:
                channel_id = ch.get('channel_id', '').strip() if isinstance(ch, dict) else str(ch).strip()
                keywords = ch.get('keywords', '') if isinstance(ch, dict) else ''
                if not channel_id:
                    continue
                downloaded = loop.run_until_complete(
                    self._fetch_channel_files(client, channel_id, limit, date_limit, file_types, keywords)
                )
                total_downloaded += downloaded
                
            return {"status": "success", "downloaded_files": total_downloaded}
        except Exception as e:
            logger.error(f"Telegram harvesting failed: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            client.disconnect()
            loop.close()
