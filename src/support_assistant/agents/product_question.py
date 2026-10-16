class ProductQuestionAgent:
    def __init__(self, retriever, answerer):
        self.retriever, self.answerer = retriever, answerer

    def run(self, question):
        hits = self.retriever.retrieve(question)
        if not hits:
            return None, hits
        return self.answerer.draft(question, hits), hits
