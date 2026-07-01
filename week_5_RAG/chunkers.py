"""Two chunking strategies: fixed-size with overlap, and structural (chapter-based)."""

FIXED_SIZE = 1000
OVERLAP = 180  # ~18% of 1000


def fixed_chunks(chapters: list[dict], size: int = FIXED_SIZE, overlap: int = OVERLAP) -> list[dict]:
    """Split each chapter into fixed-size character chunks with overlap."""
    chunks = []
    for ch_idx, ch in enumerate(chapters):
        text = ch["text"]
        start = 0
        chunk_num = 0
        while start < len(text):
            end = start + size
            chunk_text = text[start:end]
            chunk_id = f"fixed_ch{ch_idx:02d}_{chunk_num:03d}"
            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "meta_source": ch.get("source", ""),
                "meta_file": ch["filename"],
                "meta_section": ch["title"],
            })
            chunk_num += 1
            start += size - overlap
            if start >= len(text):
                break
    return chunks


def structural_chunks(chapters: list[dict], max_size: int = 4000) -> list[dict]:
    """One chunk per chapter; split large chapters by paragraph."""
    chunks = []
    for ch_idx, ch in enumerate(chapters):
        text = ch["text"]
        if len(text) <= max_size:
            chunks.append({
                "chunk_id": f"struct_ch{ch_idx:02d}_000",
                "text": text,
                "meta_source": ch.get("source", ""),
                "meta_file": ch["filename"],
                "meta_section": ch["title"],
            })
        else:
            paragraphs = text.split("\n\n")
            current = ""
            chunk_num = 0
            for para in paragraphs:
                if len(current) + len(para) + 2 > max_size and current:
                    chunks.append({
                        "chunk_id": f"struct_ch{ch_idx:02d}_{chunk_num:03d}",
                        "text": current.strip(),
                        "meta_source": ch.get("source", ""),
                        "meta_file": ch["filename"],
                        "meta_section": ch["title"],
                    })
                    chunk_num += 1
                    current = para
                else:
                    current = current + "\n\n" + para if current else para
            if current.strip():
                chunks.append({
                    "chunk_id": f"struct_ch{ch_idx:02d}_{chunk_num:03d}",
                    "text": current.strip(),
                    "meta_source": ch.get("source", ""),
                    "meta_file": ch["filename"],
                    "meta_section": ch["title"],
                })
    return chunks
