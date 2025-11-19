import logging
import logging.config

import typer

from app.core.config import settings
from app.core.logging_setup import get_logging_config
from app.services.factories import setup_embed_model
from app.services.ingest import build_or_get_vector_store
from app.services.loader import get_prepared_docs
from app.services.retrieval import VectorStoreManager

app = typer.Typer(help="RAG 数据摄取 / 向量库管理 CLI")


def configure_logging(log_level: str = "INFO") -> None:
    logging_config_dict = get_logging_config(str(settings.LOG_FILE_PATH))
    logging_config_dict["root"]["level"] = log_level
    logging.config.dictConfig(logging_config_dict)  # type: ignore[attr-defined]


@app.command()
def preview(limit: int = typer.Option(3, help="打印分割后的文档块数量"), log_level: str = "INFO"):
    """
    快速预览 loader/splitter 输出。
    """
    configure_logging(log_level)
    docs = get_prepared_docs()
    typer.echo(f"总计 {len(docs)} 个文档块。")
    for idx, doc in enumerate(docs[:limit]):
        typer.echo(f"--- Chunk #{idx+1} ---")
        typer.echo(doc.page_content[:200])
        typer.echo(f"metadata: {doc.metadata}")


@app.command()
def build(force: bool = typer.Option(False, "--force", help="是否强制重建向量库"), log_level: str = "INFO"):
    """
    执行全量向量化摄取。
    """
    configure_logging(log_level)
    embed_model = setup_embed_model("text-embedding-v4")
    vector_store = build_or_get_vector_store(
        settings.CHROMADB_COLLECTION_NAME,
        embed_model=embed_model,
        force_rebuild=force,
    )
    typer.echo(f"向量库 {settings.CHROMADB_COLLECTION_NAME} 准备就绪。当前文档数: {vector_store._collection.count()}")


@app.command()
def stats(log_level: str = "INFO"):
    """
    查看集合统计信息。
    """
    configure_logging(log_level)
    embed_model = setup_embed_model("text-embedding-v4")
    manager = VectorStoreManager(settings.CHROMADB_COLLECTION_NAME, embed_model, settings.TOP_K)
    manager.ensure_collection()
    typer.echo(manager.stats())


if __name__ == "__main__":
    app()

