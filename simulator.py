"""
Slab Allocation Simulator

Generates realistic steel mill inventory and order data,
runs the ILP allocator, and produces a planner-facing report
with LLM-generated natural language summaries.
"""

import random
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.models import Slab, Order, Plate, SlabStatus
from services.allocator import solve_allocation
from services.llm_summary import generate_planner_summary, generate_infeasibility_explanation

# --- Realistic steel mill data distributions ---

# S355 is the most common structural steel grade in UK mills
# S275 is standard, others are more specialised
GRADES = ["S355", "S355", "S355", "S275", "S275", "S420", "S460"]
QUALITY_SPECS = ["standard", "standard", "standard", "premium", "premium", "certified"]
CUSTOMERS = ["C001", "C002", "C003", "C004", "C005", "C006"]

# Slab lengths in a real plate mill typically range from 6m to 14m
SLAB_LENGTH_RANGE = (6.0, 14.0)

# Plate required lengths typically 2m to 8m
PLATE_LENGTH_RANGE = (2.0, 8.0)


def generate_slabs(n: int, seed: int = 42) -> list[Slab]:
    """Generate n realistic slabs with varying grades, specs, and lengths."""
    random.seed(seed)
    slabs = []
    for i in range(n):
        grade = random.choice(GRADES)
        quality = random.choice(QUALITY_SPECS)
        length = round(random.uniform(*SLAB_LENGTH_RANGE), 1)

        # 10% of slabs reserved, 5% incoming
        status_roll = random.random()
        if status_roll < 0.10:
            status = SlabStatus.RESERVED
        elif status_roll < 0.15:
            status = SlabStatus.INCOMING
        else:
            status = SlabStatus.AVAILABLE

        # 5% chance of customer restriction
        restrictions = []
        if random.random() < 0.05:
            restrictions = [random.choice(CUSTOMERS)]

        slabs.append(Slab(
            slab_id=f"SL-{i+1:03d}",
            length=length,
            grade=grade,
            quality_spec=quality,
            status=status,
            customer_restrictions=restrictions
        ))
    return slabs


def generate_orders(n: int, seed: int = 99) -> list[Order]:
    """Generate n realistic orders with 1-3 plates each."""
    random.seed(seed)
    orders = []
    plate_counter = 1

    for i in range(n):
        grade = random.choice(GRADES)
        quality = random.choice(QUALITY_SPECS)
        customer = random.choice(CUSTOMERS)
        num_plates = random.randint(1, 3)

        # Priority: 60% normal, 30% high, 10% urgent
        priority_roll = random.random()
        if priority_roll < 0.10:
            priority = 3  # urgent
        elif priority_roll < 0.40:
            priority = 2  # high
        else:
            priority = 1  # normal

        plates = []
        for j in range(num_plates):
            plates.append(Plate(
                plate_id=f"PL-{plate_counter:04d}",
                required_length=round(random.uniform(*PLATE_LENGTH_RANGE), 1),
                grade=grade,
                quality_spec=quality,
                customer_id=customer
            ))
            plate_counter += 1

        orders.append(Order(
            order_id=f"ORD-{i+1:03d}",
            plates=plates,
            priority=priority
        ))
    return orders


def print_report(plan, orders, slabs, use_llm=True):
    """Print a structured allocation report with optional LLM summary."""
    orders_dict = {o.order_id: o for o in orders}
    slabs_dict = {s.slab_id: s for s in slabs}

    priority_label = {1: "NORMAL", 2: "HIGH", 3: "URGENT"}

    print("=" * 60)
    print("  DEEP.META SLAB ALLOCATION REPORT")
    print("=" * 60)
    print(f"  Slabs in inventory : {len(slabs)}")
    print(f"  Orders to fulfil   : {len(orders)}")
    print(f"  Orders fulfilled   : {len(plan.allocations)}")
    print(f"  Orders failed      : {len(plan.infeasible_orders)}")
    print(f"  Total waste        : {round(plan.total_waste, 2)}m")
    print(f"  Utilisation        : {plan.utilisation_pct}%")
    print(f"  Solver time        : {plan.solve_time_seconds}s")
    print("=" * 60)

    if plan.allocations:
        print("\n  SUCCESSFUL ALLOCATIONS")
        print("  " + "-" * 56)
        for a in sorted(plan.allocations, key=lambda x: -orders_dict[x.order_id].priority):
            order = orders_dict[a.order_id]
            slab = slabs_dict[a.slab_id]
            print(f"  [{priority_label[order.priority]:6}] {a.order_id} → {a.slab_id} "
                  f"| Used {round(a.allocated_length, 2)}m / {slab.length}m "
                  f"| Waste {round(a.waste, 2)}m "
                  f"| Grade {slab.grade}")

    if plan.infeasible_orders:
        print("\n  FAILED ORDERS")
        print("  " + "-" * 56)
        for f in sorted(plan.infeasible_orders, key=lambda x: -orders_dict[x.order_id].priority):
            order = orders_dict[f.order_id]
            print(f"  [{priority_label[order.priority]:6}] {f.order_id} "
                  f"| Grade {order.grade} {order.quality_spec} "
                  f"| Needs {order.total_required_length}m "
                  f"| Reason: {f.reason}")

            if use_llm:
                print("\n  AI Explanation:")
                try:
                    explanation = generate_infeasibility_explanation(order, slabs, f.reason)
                    for line in explanation.strip().split("\n"):
                        print(f"    {line}")
                except Exception:
                    print("    (LLM explanation unavailable)")
                print()

    if use_llm:
        print("\n" + "=" * 60)
        print("  AI PLANNER SUMMARY")
        print("=" * 60)
        try:
            summary = generate_planner_summary(plan, orders, slabs)
            for line in summary.strip().split("\n"):
                print(f"  {line}")
        except Exception:
            print("  (LLM summary unavailable)")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    print("\nGenerating steel mill inventory and orders...")

    slabs = generate_slabs(n=30)
    orders = generate_orders(n=20)

    available = sum(1 for s in slabs if s.status == SlabStatus.AVAILABLE)
    print(f"Generated {len(slabs)} slabs ({available} available) and {len(orders)} orders\n")
    print("Running ILP optimisation...\n")

    plan = solve_allocation(slabs, orders)

    use_llm = "--no-llm" not in sys.argv
    print_report(plan, orders, slabs, use_llm=use_llm)
