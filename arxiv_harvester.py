import arxiv
import os
import tarfile
import tempfile
import pypandoc
import json
import time
import requests

# arxiv >= 4.0.0 removed Result.download_pdf / Result.download_source, so we
# fetch the artifacts directly over HTTP. A descriptive UA avoids arXiv blocks.
ARXIV_USER_AGENT = "SamvitResearchHarvester/1.0 (+https://arxiv.org)"

class ArxivHarvester:
    def __init__(self, download_dir="RawMaterials"):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        
        # Ensure pandoc is available for pypandoc
        try:
            pypandoc.get_pandoc_version()
        except OSError:
            print("Pandoc not found. Attempting to download via pypandoc...")
            try:
                pypandoc.download_pandoc()
            except Exception as e:
                print(f"Failed to download Pandoc: {e}")

    def search(self, query, max_results=10, sort_by='relevance'):
        """Search arXiv and return a list of results."""
        if sort_by == 'lastUpdatedDate':
            sort_criterion = arxiv.SortCriterion.LastUpdatedDate
        elif sort_by == 'submittedDate':
            sort_criterion = arxiv.SortCriterion.SubmittedDate
        else:
            sort_criterion = arxiv.SortCriterion.Relevance

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_criterion
        )
        
        client = arxiv.Client(page_size=max_results, delay_seconds=3.0, num_retries=5)
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                results = []
                for result in client.results(search):
                    results.append({
                        "id": result.entry_id.split('/')[-1],
                        "title": result.title,
                        "authors": [a.name for a in result.authors],
                        "summary": result.summary,
                        "published": result.published.strftime('%Y-%m-%d'),
                        "pdf_url": result.pdf_url,
                        "entry_id": result.entry_id,
                        "categories": result.categories
                    })
                return results
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 5)
                else:
                    raise e

    def _download_url(self, url, filename):
        """Stream a URL to the download dir; return the local path."""
        filepath = os.path.join(self.download_dir, filename)
        headers = {"User-Agent": ARXIV_USER_AGENT}
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=90,
                                    stream=True, allow_redirects=True)
                if resp.status_code == 429:
                    time.sleep((attempt + 1) * 5)
                    continue
                resp.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return filepath
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep((attempt + 1) * 3)
                else:
                    raise

    def download_pdf(self, paper_id):
        """Download the PDF for a given paper ID."""
        client = arxiv.Client(delay_seconds=3.0, num_retries=5)
        paper = next(client.results(arxiv.Search(id_list=[paper_id])))
        url = paper.pdf_url
        if not url:
            raise ValueError(f"No PDF URL available for arXiv paper {paper_id}.")
        return self._download_url(url, f"{paper_id}.pdf")

    def download_source(self, paper_id):
        """Download the LaTeX source tarball for a given paper ID."""
        # e-print is arXiv's canonical source-download endpoint.
        url = f"https://arxiv.org/e-print/{paper_id}"
        return self._download_url(url, f"{paper_id}_source.tar.gz")

    def _find_main_tex(self, tex_files):
        """Pick the main LaTeX file among many.

        arXiv sources routinely ship dozens of .tex files (sections included via
        \\input, appendices, style snippets). The real entry point is the one
        that carries \\documentclass and \\begin{document}; among candidates we
        prefer the one with the largest document body (the paper itself, not a
        thin wrapper).
        """
        best = None
        best_score = -1
        for tex in tex_files:
            try:
                with open(tex, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except OSError:
                continue
            has_doc = '\\begin{document}' in content
            has_class = '\\documentclass' in content
            if not (has_doc or has_class):
                continue
            # Score by presence of the real markers plus body size, so the main
            # manuscript beats a minimal wrapper that just \inputs everything.
            score = len(content)
            if has_doc:
                score += 1_000_000
            if has_class:
                score += 500_000
            if score > best_score:
                best_score = score
                best = tex
        return best or (tex_files[0] if tex_files else None)

    def convert_latex_to_md(self, tar_path):
        """Unpack a LaTeX source tarball and convert the main .tex file to Markdown."""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with tarfile.open(tar_path, "r:gz") as tar:
                    tar.extractall(path=temp_dir)

                # Find the main .tex file
                tex_files = []
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith(".tex"):
                            tex_files.append(os.path.join(root, file))

                if not tex_files:
                    return None, "No .tex files found in source."

                main_tex = self._find_main_tex(tex_files)
                if not main_tex:
                    return None, "Could not identify a main .tex file."

                # Convert to Markdown using Pandoc.
                #   --wrap=none        : avoid awkward hard line breaks in Obsidian
                #   --resource-path    : let pandoc resolve \input/\include and
                #                        \graphics relative to the source tree
                main_dir = os.path.dirname(main_tex)
                resource_path = os.pathsep.join([main_dir, temp_dir])
                output = pypandoc.convert_file(
                    main_tex, 'markdown', format='latex',
                    extra_args=['--wrap=none', f'--resource-path={resource_path}'])
                return output, None
            except Exception as e:
                return None, f"LaTeX conversion error: {str(e)}"

if __name__ == "__main__":
    # Quick test
    harvester = ArxivHarvester()
    print("Searching for finance papers...")
    results = harvester.search("computational finance", max_results=2)
    for r in results:
        print(f"- {r['title']} ({r['id']})")
