import logging

from app.db.session import SessionLocal, init_db
from app.models.knowledge_models import KnowledgeBase
from sqlmodel import select

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def run_test():
    log.info("Starting test")

    log.info("Initializing database")
    init_db()
    log.info("Database initialized")

    try:
        with SessionLocal() as db:
            
            log.info("Creating knowledge base")

            kb = KnowledgeBase(name="Test KB")
            db.add(kb)

            try:
                db.commit()
            except Exception as e:
                log.error(f"Error committing knowledge base: {e}")
                db.rollback()

        statement = select(KnowledgeBase).where(KnowledgeBase.name == "Test KB")
        result = db.execute(statement).first()
        print("=========")
        print(result)
        print("=========")
        
        print(kb)

        all_kbs = db.query(KnowledgeBase).all()

        if not all_kbs:
            log.error("No knowledge bases found")
            return
        else:
            for kb in all_kbs:
                log.info(f"Knowledge base: {kb.name}")

        log.info("Test completed successfully")

    except Exception as e:
        log.error(f"Error: {e}")

if __name__ == "__main__":
    run_test()