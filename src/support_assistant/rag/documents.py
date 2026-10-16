import hashlib
import json
from pathlib import Path
import yaml
from support_assistant.domain.evidence import Document

def load_documents(kb_dir: Path) -> list[Document]:
    root = kb_dir.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    docs = []
    seen = set()
    for entry in manifest["documents"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or path.suffix != ".md":
            raise ValueError("Manifest contains an invalid document path")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"Document hash mismatch: {entry['document_id']}")
        text = raw.decode("utf-8")
        parts = text.split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError("Expected YAML front matter")
        metadata = yaml.safe_load(parts[1])
        for key in ("document_id", "title", "version"):
            if str(metadata[key]) != str(entry[key]):
                raise ValueError(f"Manifest metadata mismatch: {key}")
        if entry["document_id"] in seen:
            raise ValueError("Duplicate document ID")
        seen.add(entry["document_id"])
        body = parts[2].strip()
        if not body:
            raise ValueError("Empty document")
        docs.append(Document(entry["document_id"], entry["title"], entry["path"],
            entry["version"], body, digest))
    if not docs or len(docs) != manifest["document_count"]:
        raise ValueError("Document count mismatch")
    return docs

def corpus_fingerprint(documents: list[Document]) -> str:
    payload = sorted((d.document_id, d.path, d.version, d.sha256) for d in documents)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
