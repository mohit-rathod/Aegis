from support_assistant.adapters.embeddings.sentence_transformer import SentenceTransformerEmbedder
from support_assistant.adapters.retrieval.numpy_index import NumpyIndex
from support_assistant.adapters.groq.client import GroqJsonLLM
from support_assistant.rag.documents import load_documents
from support_assistant.rag.retriever import Retriever
from support_assistant.rag.grounding import GroundedAnswerer
from support_assistant.agents.product_question import ProductQuestionAgent
from support_assistant.safety.input_guard import SemanticInputGuard
from support_assistant.safety.output_guard import GroundingOutputGuard
from support_assistant.application.support_service import GuardedRAGService

def build_retriever(settings):
    embedder = SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_revision)
    return Retriever(NumpyIndex.load(settings.index_dir), load_documents(settings.kb_dir), embedder, settings)

def build_service(settings):
    retriever = build_retriever(settings)
    llm = GroqJsonLLM(settings.groq_key, settings.groq_model, settings.provider_timeout)
    service = GuardedRAGService(SemanticInputGuard(llm),
        ProductQuestionAgent(retriever, GroundedAnswerer(llm)), GroundingOutputGuard(llm))
    return service, llm
