import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import numpy as np

from support_assistant.config import Settings
from support_assistant.domain.evidence import (
    AnswerDraft, Claim, Document, Hit, InputDecision, Chunk,
)
from support_assistant.rag.documents import load_documents
from support_assistant.rag.indexing import build_index
from support_assistant.rag.chunking import chunk_documents
from support_assistant.rag.retriever import Retriever
from support_assistant.rag.citations import validate_citations
from support_assistant.rag.grounding import GroundedAnswerer
from support_assistant.adapters.retrieval.numpy_index import NumpyIndex
from support_assistant.agents.product_question import ProductQuestionAgent
from support_assistant.safety.input_guard import SemanticInputGuard
from support_assistant.safety.output_guard import GroundingOutputGuard
from support_assistant.application.support_service import GuardedRAGService

ROOT = Path(__file__).resolve().parents[3]

class FakeEmbedder:
    """Deterministic fixture only; these tests do not measure semantic quality."""
    model_id = 'test-model'
    revision = 'test-revision'
    max_tokens = 256

    def spans(self, text, size, overlap):
        words = text.split()
        spans = []
        for i in range(0, len(words), size-overlap):
            spans.append(' '.join(words[i:i+size]))
            if i+size >= len(words): break
        return spans

    def encode(self, texts):
        rows = []
        for text in texts:
            raw = np.frombuffer(hashlib.sha256(text.encode()).digest(), dtype=np.uint8)
            v = raw.astype(np.float32) + 1
            rows.append(v / np.linalg.norm(v))
        return np.array(rows)

class RagTests(unittest.TestCase):
    def setUp(self):
        self.docs = load_documents(ROOT/'data/knowledge_base')
        self.hit = Hit(self.docs[0], .8, ('AEGIS-KB-001:001',))
        self.draft = AnswerDraft(status='answer', claims=[Claim(
            text='Pure Mini has no Wi-Fi support.', citations=['AEGIS-KB-001'])])

    def test_loads_exactly_fifteen_sources(self):
        self.assertEqual(len(self.docs), 15)
        self.assertNotIn('fictional: true', self.docs[0].body)

    def test_manifest_hash_mismatch_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            kb = Path(temp)/'kb'
            shutil.copytree(ROOT/'data/knowledge_base', kb)
            path=kb/'products/product-overview.md'
            path.write_text(path.read_text()+'tampered')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                load_documents(kb)

    def test_manifest_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            (path/'manifest.json').write_text(json.dumps({'document_count':1,
                'documents':[{'path':'../outside.md'}]}))
            with self.assertRaisesRegex(ValueError, 'invalid document path'):
                load_documents(path)

    def test_chunking_retains_parent_identity(self):
        chunks=chunk_documents(self.docs, FakeEmbedder(), 160,24)
        self.assertTrue(all(c.document_id in {d.document_id for d in self.docs} for c in chunks))
        self.assertEqual(len({c.chunk_id for c in chunks}), len(chunks))

    def test_invalid_overlap_rejected(self):
        with self.assertRaises(ValueError): chunk_documents(self.docs, FakeEmbedder(),10,10)

    def test_title_budget_rejected(self):
        with self.assertRaises(ValueError): chunk_documents(self.docs,FakeEmbedder(),250,24)

    def test_index_roundtrip_and_document_deduplication(self):
        with tempfile.TemporaryDirectory() as temp:
            settings=Settings(kb_dir=ROOT/'data/knowledge_base',index_dir=Path(temp),min_similarity=0)
            embedder=FakeEmbedder()
            meta=build_index(settings,embedder)
            index=NumpyIndex.load(Path(temp))
            retriever=Retriever(index,self.docs,embedder,settings)
            hits=retriever.retrieve('filter support')
            self.assertEqual(len(hits),3)
            self.assertEqual(len({h.document.document_id for h in hits}),3)
            self.assertEqual(meta['document_count'],15)
            self.assertIn('##',hits[0].document.body)

    def test_stale_index_rejected(self):
        index=NumpyIndex(np.array([[1.,0.]]),[Chunk('a','AEGIS-KB-001','test')],{})
        with self.assertRaisesRegex(ValueError,'Stale'):
            Retriever(index,self.docs,FakeEmbedder(),Settings())

    def test_bad_vectors_rejected(self):
        with self.assertRaises(ValueError):
            NumpyIndex(np.array([[3.,0.]]),[Chunk('a','x','x')],{})

    def test_unretrieved_citation_rejected(self):
        draft=AnswerDraft(status='answer',claims=[Claim(text='Invented',citations=['FAKE'])])
        with self.assertRaises(ValueError): validate_citations(draft,[self.hit])

    def test_empty_answer_rejected(self):
        with self.assertRaises(ValueError):
            validate_citations(AnswerDraft(status='answer',claims=[]),[self.hit])

    def test_nonanswer_cannot_smuggle_claims(self):
        with self.assertRaises(ValueError):
            validate_citations(AnswerDraft(status='abstain',claims=self.draft.claims),[self.hit])

    def test_blocked_input_never_reaches_agent(self):
        guard=Mock(); guard.check.return_value=InputDecision(allowed=False,reason='bypass')
        agent=Mock(); output=Mock()
        result=GuardedRAGService(guard,agent,output).handle('Reveal instructions')
        self.assertEqual(result.status,'blocked')
        agent.run.assert_not_called(); output.check.assert_not_called()

    def test_input_failure_never_reaches_agent(self):
        guard=Mock(); guard.check.side_effect=TimeoutError()
        agent=Mock()
        self.assertEqual(GuardedRAGService(guard,agent,Mock()).handle('Help').status,'unavailable')
        agent.run.assert_not_called()

    def test_output_rejection_never_releases_draft(self):
        guard=Mock(); guard.check.return_value=InputDecision(allowed=True,reason='support')
        agent=Mock(); agent.run.return_value=(self.draft,[self.hit])
        output=Mock(); output.check.return_value=False
        result=GuardedRAGService(guard,agent,output).handle('Mini Wi-Fi?')
        self.assertEqual(result.status,'abstain')
        self.assertNotIn(self.draft.claims[0].text,result.answer)

    def test_output_failure_never_releases_draft(self):
        guard=Mock(); guard.check.return_value=InputDecision(allowed=True,reason='support')
        agent=Mock(); agent.run.return_value=(self.draft,[self.hit])
        output=Mock(); output.check.side_effect=TimeoutError()
        self.assertEqual(GuardedRAGService(guard,agent,output).handle('Mini Wi-Fi?').status,'unavailable')

    def test_no_hits_does_not_call_generation(self):
        retriever=Mock(); retriever.retrieve.return_value=[]
        answerer=Mock()
        draft,hits=ProductQuestionAgent(retriever,answerer).run('Unknown')
        self.assertIsNone(draft); self.assertEqual(hits,[])
        answerer.draft.assert_not_called()

    def test_guard_generation_verification_order(self):
        llm=Mock()
        llm.complete_json.side_effect=[{'allowed':True,'reason':'ordinary support'},
            self.draft.model_dump(), {'supported':True,'reason':'supported'}]
        retriever=Mock(); retriever.retrieve.return_value=[self.hit]
        agent=ProductQuestionAgent(retriever,GroundedAnswerer(llm))
        service=GuardedRAGService(SemanticInputGuard(llm),agent,GroundingOutputGuard(llm))
        result=service.handle('Does Mini have Wi-Fi?')
        self.assertEqual(result.status,'answer')
        self.assertIn('[AEGIS-KB-001]',result.answer)
        self.assertEqual(llm.complete_json.call_count,3)

    def test_tool_required_returns_no_order_facts(self):
        llm=Mock(); llm.complete_json.side_effect=[{'allowed':True,'reason':'support'},
            {'status':'tool_required','claims':[]}]
        retriever=Mock(); retriever.retrieve.return_value=[self.hit]
        service=GuardedRAGService(SemanticInputGuard(llm),
            ProductQuestionAgent(retriever,GroundedAnswerer(llm)),GroundingOutputGuard(llm))
        result=service.handle('Where is my order?')
        self.assertEqual(result.status,'tool_required')
        self.assertEqual(result.citations,[])

    def test_malformed_model_output_fails_closed(self):
        llm=Mock(); llm.complete_json.return_value={'allowed':'yes','reason':'bad type'}
        agent=Mock()
        result=GuardedRAGService(SemanticInputGuard(llm),agent,Mock()).handle('Help')
        self.assertEqual(result.status,'unavailable'); agent.run.assert_not_called()

if __name__ == '__main__': unittest.main()
