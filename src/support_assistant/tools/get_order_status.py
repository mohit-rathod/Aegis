from support_assistant.domain.conversation import SupportError

def get_order_status(order):
    state=order.get("refund_status","none")
    if state=="approved":
        raise SupportError("inconsistent_refund_state")
    if state=="approved_and_initiated" and (not order.get("refund_initiated_at") or
            order.get("refund_destination")!="original_payment_source"):
        raise SupportError("inconsistent_refund_state")
    return {"order_id":order["order_id"],"status":order["status"],
        "estimated_delivery":order.get("estimated_delivery"),"refund_status":state,
        "refund_initiated_at":order.get("refund_initiated_at"),
        "refund_destination":order.get("refund_destination"),"source":"authorized_order_store"}
