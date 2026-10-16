from pydantic import BaseModel, ConfigDict, Field

class OrderArguments(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    order_id: str=Field(pattern=r"^AEG-[0-9]{4,12}$")

TOOLS=[{"type":"function","function":{"name":name,"description":description,
    "parameters":OrderArguments.model_json_schema()}} for name,description in [
    ("get_order_status","Read an authorized order's shipping status and recorded refund status. Never execute a refund."),
    ("check_return_eligibility","Check whether an authorized order can request a return; this does not approve or initiate a refund.")]]
