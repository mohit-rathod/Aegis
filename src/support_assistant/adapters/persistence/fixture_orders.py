import json
from pathlib import Path

class FixtureOrders:
    def __init__(self,path):
        records=json.loads(Path(path).read_text())
        self.orders={r["order_id"]:r for r in records}
        if len(self.orders)!=len(records): raise ValueError("Duplicate order fixture")
        for order in records:
            if order.get("refund_status")=="approved_and_initiated":
                if not order.get("refund_initiated_at") or order.get("refund_destination")!="original_payment_source":
                    raise ValueError("Invalid confirmed refund fixture")

    def get(self,order_id):
        order=self.orders.get(order_id)
        return dict(order) if order else None
