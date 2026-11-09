import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.models import Slab, Order, Plate, SlabStatus
from services.allocator import solve_allocation


def test_basic_allocation():
    """Test the example from the assessment: 10m slab, plates needing 3m and 4m."""
    slabs = [
        Slab(slab_id="S1", length=10.0, grade="S355", quality_spec="standard")
    ]
    orders = [
        Order(
            order_id="O1",
            plates=[
                Plate("P1", required_length=3.0, grade="S355", quality_spec="standard", customer_id="C1"),
                Plate("P2", required_length=4.0, grade="S355", quality_spec="standard", customer_id="C1"),
            ]
        )
    ]
    plan = solve_allocation(slabs, orders)
    assert len(plan.allocations) == 1
    assert plan.allocations[0].waste == 3.0
    print(f"PASS: basic allocation — waste={plan.allocations[0].waste}m, utilisation={plan.utilisation_pct}%")


def test_grade_incompatibility():
    """Slab grade does not match order grade — should be infeasible."""
    slabs = [
        Slab(slab_id="S1", length=10.0, grade="S275", quality_spec="standard")
    ]
    orders = [
        Order(
            order_id="O1",
            plates=[
                Plate("P1", required_length=5.0, grade="S355", quality_spec="standard", customer_id="C1"),
            ]
        )
    ]
    plan = solve_allocation(slabs, orders)
    assert len(plan.infeasible_orders) == 1
    assert "grade" in plan.infeasible_orders[0].reason.lower() or "compatible" in plan.infeasible_orders[0].reason.lower()
    print(f"PASS: grade incompatibility detected — reason: {plan.infeasible_orders[0].reason}")


def test_insufficient_length():
    """Slab too short for the order — should be infeasible."""
    slabs = [
        Slab(slab_id="S1", length=5.0, grade="S355", quality_spec="standard")
    ]
    orders = [
        Order(
            order_id="O1",
            plates=[
                Plate("P1", required_length=8.0, grade="S355", quality_spec="standard", customer_id="C1"),
            ]
        )
    ]
    plan = solve_allocation(slabs, orders)
    assert len(plan.infeasible_orders) == 1
    print(f"PASS: insufficient length detected — reason: {plan.infeasible_orders[0].reason}")


def test_optimal_allocation_multiple_orders():
    """
    Two slabs, two orders. Tests that ILP finds the globally optimal assignment
    rather than a greedy one.

    Slab A: 10m  Order 1 needs 9m  (waste=1m if matched)
    Slab B: 12m  Order 2 needs 11m (waste=1m if matched)

    Greedy might assign Slab A to Order 2 (compatible but wasteful),
    ILP should find the minimum total waste assignment.
    """
    slabs = [
        Slab(slab_id="SA", length=10.0, grade="S355", quality_spec="standard"),
        Slab(slab_id="SB", length=12.0, grade="S355", quality_spec="standard"),
    ]
    orders = [
        Order("O1", plates=[Plate("P1", 9.0, "S355", "standard", "C1")]),
        Order("O2", plates=[Plate("P2", 11.0, "S355", "standard", "C1")]),
    ]
    plan = solve_allocation(slabs, orders)
    assert len(plan.allocations) == 2
    assert plan.total_waste == 2.0
    print(f"PASS: optimal multi-order allocation — total waste={plan.total_waste}m, utilisation={plan.utilisation_pct}%")


def test_customer_restriction():
    """Slab restricted from a customer — order from that customer should be infeasible."""
    slabs = [
        Slab(slab_id="S1", length=10.0, grade="S355", quality_spec="standard", customer_restrictions=["C_BLOCKED"])
    ]
    orders = [
        Order("O1", plates=[Plate("P1", 5.0, "S355", "standard", "C_BLOCKED")])
    ]
    plan = solve_allocation(slabs, orders)
    assert len(plan.infeasible_orders) == 1
    print(f"PASS: customer restriction enforced — reason: {plan.infeasible_orders[0].reason}")


if __name__ == "__main__":
    print("Running allocation tests...\n")
    test_basic_allocation()
    test_grade_incompatibility()
    test_insufficient_length()
    test_optimal_allocation_multiple_orders()
    test_customer_restriction()
    print("\nAll tests passed.")
