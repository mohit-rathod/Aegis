import argparse
import asyncio
import json
import uuid
from support_assistant.bootstrap_part_a import create_runtime
from support_assistant.domain.conversation import Turn
from support_assistant.observability.logging import configure_logging

async def run(args):
    runtime=await create_runtime()
    try:
        if args.command=="metrics":
            print(json.dumps(await runtime.cache.metrics(),indent=2));return
        # Local CLI demo identity is a trusted operator fixture, not production login.
        session=await runtime.store.create(args.customer)
        print(f"Demo session: {session.session_id}")
        while True:
            try: text=await asyncio.to_thread(input,"You: ")
            except EOFError: break
            if text.strip().lower() in ["/quit","/exit"]: break
            if len(text)>2000:
                print("Assistant: Your message is too long. Please shorten it and try again.");continue
            result=await runtime.service.handle(args.customer,session.session_id,
                Turn(turn_id=uuid.uuid4().hex,text=text))
            print("Assistant:",result.answer)
            if result.session_state=="terminated": break
        print("Classifier metrics:",json.dumps(await runtime.cache.metrics()))
    finally: await runtime.aclose()

def main():
    parser=argparse.ArgumentParser(description="Guarded three-intent Aegis support")
    parser.add_argument("command",choices=["chat","metrics"])
    parser.add_argument("--customer",choices=["customer-a","customer-b"],default="customer-a")
    args=parser.parse_args()
    configure_logging()
    try: asyncio.run(run(args))
    except KeyboardInterrupt: pass

if __name__=="__main__": main()
