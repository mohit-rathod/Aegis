from support_assistant.domain.conversation import SupportError

def authorize_order(order,customer_id):
    if not order or order.get("customer_id") != customer_id:
        raise SupportError("order_not_available")
