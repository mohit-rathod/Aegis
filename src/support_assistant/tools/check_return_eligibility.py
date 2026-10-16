from datetime import date

POLICY_ID="AEGIS-KB-011"
POLICY_VERSION="1.0.0"

def check_return_eligibility(order,today):
    result={"order_id":order["order_id"],"policy_id":POLICY_ID,"policy_version":POLICY_VERSION,
        "evaluated_on":today.isoformat(),"eligibility":"review_required","reason":"Required information needs review"}
    if order.get("channel")=="marketplace":
        return {**result,"eligibility":"ineligible","reason":"Contact the original marketplace seller"}
    required=["channel","delivered_on","accessories_complete","condition","product_type"]
    if any(order.get(k) is None for k in required): return result
    if order["channel"]!="direct": return result
    try: days=(today-date.fromisoformat(order["delivered_on"])).days
    except ValueError: return result
    if days<0: return result
    if days>14: return {**result,"eligibility":"ineligible","reason":"Outside the 14-calendar-day return window"}
    if order["accessories_complete"] is not True or order["condition"] not in ["unused","inspected","used_good"]:
        return result
    if order["product_type"]=="cartridge":
        if order.get("sealed") is not True or order["condition"]!="unused":
            return {**result,"reason":"Opened or used cartridges require defect review"}
    elif order["product_type"]!="purifier": return result
    return {**result,"eligibility":"eligible","reason":"Within 14 days and recorded conditions meet the return-request policy"}
