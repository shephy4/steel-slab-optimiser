import json
import os
from groq import Groq
from models.models import AllocationPlan, Order, Slab


def get_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")
    return Groq(api_key=api_key)


def generate_planner_summary(
    plan: AllocationPlan,
    orders: list[Order],
    slabs: list[Slab]
) -> str:
    """
    Use an LLM to generate a natural language summary of the allocation plan
    suitable for a mill planner to read and act on.
    """
    client = get_client()

    orders_dict = {o.order_id: o for o in orders}
    slabs_dict = {s.slab_id: s for s in slabs}

    allocation_details = []
    for a in plan.allocations:
        order = orders_dict.get(a.order_id)
        slab = slabs_dict.get(a.slab_id)
        allocation_details.append({
            "order_id": a.order_id,
            "slab_id": a.slab_id,
            "grade": slab.grade if slab else "unknown",
            "quality_spec": slab.quality_spec if slab else "unknown",
            "slab_length": slab.length if slab else 0,
            "allocated_length": a.allocated_length,
            "waste_m": round(a.waste, 2),
            "priority": order.priority if order else 1,
            "plates": a.plates
        })

    infeasible_details = []
    for f in plan.infeasible_orders:
        order = orders_dict.get(f.order_id)
        infeasible_details.append({
            "order_id": f.order_id,
            "priority": order.priority if order else 1,
            "plates": f.plates,
            "reason": f.reason
        })

    prompt = f"""You are an AI assistant helping steel mill planners understand their daily slab allocation plan.

Here is the allocation result:

SUMMARY STATS:
- Total orders fulfilled: {len(plan.allocations)}
- Total orders failed: {len(plan.infeasible_orders)}
- Total waste: {round(plan.total_waste, 2)}m
- Overall utilisation: {plan.utilisation_pct}%
- Solver time: {plan.solve_time_seconds}s

SUCCESSFUL ALLOCATIONS:
{json.dumps(allocation_details, indent=2)}

FAILED ORDERS:
{json.dumps(infeasible_details, indent=2)}

Write a clear, concise operations summary for the planner. Use plain English, no jargon.
Cover:
1. Overall performance (utilisation, waste)
2. Any urgent/high priority orders that failed and why
3. Any patterns in the failures (e.g. grade shortages)
4. One or two actionable recommendations

Keep it under 200 words. Write it as if briefing a senior planner at the start of their shift."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400
    )

    return response.choices[0].message.content


def generate_infeasibility_explanation(
    order: Order,
    available_slabs: list[Slab],
    reason: str
) -> str:
    """
    Generate a plain English explanation for why a specific order
    could not be fulfilled, with an actionable suggestion.
    """
    client = get_client()

    compatible_slabs = [
        {
            "slab_id": s.slab_id,
            "length": s.length,
            "grade": s.grade,
            "quality_spec": s.quality_spec,
            "status": s.status.value
        }
        for s in available_slabs
        if s.grade == order.grade and s.quality_spec == order.quality_spec
    ]

    prompt = f"""You are an AI assistant helping a steel mill planner understand why an order could not be fulfilled.

ORDER DETAILS:
- Order ID: {order.order_id}
- Priority: {"URGENT" if order.priority == 3 else "HIGH" if order.priority == 2 else "NORMAL"}
- Total length required: {order.total_required_length}m
- Grade: {order.grade}
- Quality spec: {order.quality_spec}
- Number of plates: {len(order.plates)}

SYSTEM REASON: {reason}

AVAILABLE SLABS OF MATCHING GRADE/QUALITY:
{json.dumps(compatible_slabs, indent=2) if compatible_slabs else "None found"}

Write a brief (2-3 sentence) plain English explanation for the planner, and suggest one concrete action they can take.
Do not use technical jargon. Be direct and practical."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150
    )

    return response.choices[0].message.content
