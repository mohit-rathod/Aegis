from support_assistant.domain.conversation import SupportError


class GuardedDispatcher:
    def __init__(self, authority, handlers):
        self.authority, self.handlers = authority, handlers

    async def dispatch(self, approved, route):
        self.authority.verify(approved)
        if route.intent not in self.handlers:
            raise SupportError("unregistered_intent")
        return await self.handlers[route.intent].run(approved)
