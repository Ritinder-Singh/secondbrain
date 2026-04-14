"""
Base connector interface — adapter pattern.
All connectors implement fetch_documents() + sync().
"""
from abc import ABC, abstractmethod


class BaseConnector(ABC):

    @abstractmethod
    def fetch_documents(self) -> list[dict]:
        """
        Fetch raw content from the source.
        Returns list of dicts compatible with ingestion/pipeline.py ingest().
        Each dict must have at minimum: {source (str)} — a URL or file path.
        """

    def sync(self, dry_run: bool = False) -> dict:
        """
        Fetch all documents and ingest them via the pipeline.
        Returns summary: {connector, ingested, skipped, errors}
        """
        from ingestion.pipeline import ingest

        docs = self.fetch_documents()
        ingested, skipped, errors = 0, 0, []

        for doc in docs:
            if dry_run:
                print(f"  [dry-run] would ingest: {doc['source']}")
                skipped += 1
                continue
            try:
                ingest(
                    doc["source"],
                    para_category=doc.get("para_category", "Resources"),
                    tags=doc.get("tags", []),
                )
                ingested += 1
            except Exception as e:
                errors.append({"source": doc["source"], "error": str(e)})

        return {
            "connector": self.__class__.__name__,
            "ingested": ingested,
            "skipped": skipped,
            "errors": errors,
        }
