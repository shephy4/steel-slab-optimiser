from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.models import Slab, Order, Plate, SlabStatus
from services.allocator import solve_allocation
from services.llm_summary import generate_planner_summary, generate_infeasibility_explanation

app = FastAPI(
    title="Deep.Meta Slab Allocation API",
    description="Optimal slab-to-order allocation for steel plate mills",
    version="1.0.0"
)


# --- Request/Response Schemas ---

class PlateRequest(BaseModel):
    plate_id: str
    required_length: float
    grade: str
    quality_spec: str
    customer_id: str


class OrderRequest(BaseModel):
    order_id: str
    plates: list[PlateRequest]
    must_fulfil_together: bool = True
    priority: int = 1


class SlabRequest(BaseModel):
    slab_id: str
    length: float
    grade: str
    quality_spec: str
    status: str = "available"
    reserved_for: Optional[str] = None
    customer_restrictions: list[str] = []


class AllocationRequest(BaseModel):
    slabs: list[SlabRequest]
    orders: list[OrderRequest]


class AllocationResultResponse(BaseModel):
    order_id: str
    slab_id: str
    allocated_length: float
    waste: float
    plates: list[str]
    feasible: bool
    reason: Optional[str] = None
    ai_explanation: Optional[str] = None


class AllocationPlanResponse(BaseModel):
    allocations: list[AllocationResultResponse]
    infeasible_orders: list[AllocationResultResponse]
    total_waste: float
    utilisation_pct: float
    solve_time_seconds: float
    planner_summary: Optional[str] = None


# --- Endpoints ---

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/allocate", response_model=AllocationPlanResponse)
def allocate(request: AllocationRequest):
    """
    Run the ILP-based slab allocation optimiser.

    Returns the optimal allocation plan minimising total yield loss,
    along with any infeasible orders, the reason they could not be fulfilled,
    and an AI-generated planner summary.
    """
    try:
        slabs = [
            Slab(
                slab_id=s.slab_id,
                length=s.length,
                grade=s.grade,
                quality_spec=s.quality_spec,
                status=SlabStatus(s.status),
                reserved_for=s.reserved_for,
                customer_restrictions=s.customer_restrictions
            )
            for s in request.slabs
        ]

        orders = [
            Order(
                order_id=o.order_id,
                plates=[
                    Plate(
                        plate_id=p.plate_id,
                        required_length=p.required_length,
                        grade=p.grade,
                        quality_spec=p.quality_spec,
                        customer_id=p.customer_id
                    )
                    for p in o.plates
                ],
                must_fulfil_together=o.must_fulfil_together,
                priority=o.priority
            )
            for o in request.orders
        ]

        plan = solve_allocation(slabs, orders)

        # Build infeasible results with AI explanations
        infeasible_results = []
        for a in plan.infeasible_orders:
            order = next(o for o in orders if o.order_id == a.order_id)
            ai_explanation = None
            try:
                ai_explanation = generate_infeasibility_explanation(order, slabs, a.reason)
            except Exception:
                pass
            infeasible_results.append(AllocationResultResponse(
                **{k: v for k, v in a.__dict__.items()},
                ai_explanation=ai_explanation
            ))

        # Generate overall planner summary
        planner_summary = None
        try:
            planner_summary = generate_planner_summary(plan, orders, slabs)
        except Exception:
            pass

        return AllocationPlanResponse(
            allocations=[
                AllocationResultResponse(**a.__dict__) for a in plan.allocations
            ],
            infeasible_orders=infeasible_results,
            total_waste=round(plan.total_waste, 2),
            utilisation_pct=plan.utilisation_pct,
            solve_time_seconds=plan.solve_time_seconds,
            planner_summary=planner_summary
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
