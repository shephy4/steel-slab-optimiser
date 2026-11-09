import time
import pulp
from models.models import Slab, Order, AllocationResult, AllocationPlan


def calculate_required_length(slab: Slab, plate_order: Order) -> float:
    """
    Stub for the provided function.
    In production this integrates with Deep.Meta's Deep.Optimiser PhyX,
    which uses real-time furnace sensor data and material science models
    to compute the exact slab length required for rolling.
    For now we sum plate required lengths directly.
    """
    return plate_order.total_required_length


def is_compatible(slab: Slab, order: Order) -> bool:
    """Check if a slab is compatible with an order based on operational constraints."""
    if not slab.is_available:
        return False
    if slab.grade != order.grade:
        return False
    if slab.quality_spec != order.quality_spec:
        return False
    customer_ids = {p.customer_id for p in order.plates}
    for customer_id in customer_ids:
        if customer_id in slab.customer_restrictions:
            return False
    return True


def solve_allocation(slabs: list[Slab], orders: list[Order]) -> AllocationPlan:
    """
    Solve the slab-to-order allocation problem using Integer Linear Programming.

    Decision variables:
        x[s, o] = 1 if slab s is assigned to order o, else 0
        y[o]    = 1 if order o is fulfilled, else 0

    Objective:
        Maximise weighted fulfilment (by order priority), then minimise waste.

            Maximise: M * sum(priority[o] * y[o]) - sum(waste[s,o] * x[s,o])

        Where M is a large constant ensuring fulfilment always takes priority
        over waste minimisation. Higher priority orders are fulfilled first.

    Constraints:
        1. Each slab assigned to at most one order
        2. Each order assigned to at most one slab
        3. y[o] = 1 only if a slab is assigned to order o
        4. Only compatible slab-order pairs considered
    """
    start_time = time.time()

    slabs_dict = {slab.slab_id: slab for slab in slabs}
    orders_dict = {order.order_id: order for order in orders}

    # Pre-compute compatible pairs and required lengths
    compatible_pairs = []
    required_lengths = {}

    for slab in slabs:
        for order in orders:
            if is_compatible(slab, order):
                req = calculate_required_length(slab, order)
                if req <= slab.length:
                    compatible_pairs.append((slab.slab_id, order.order_id))
                    required_lengths[(slab.slab_id, order.order_id)] = req

    prob = pulp.LpProblem("SlabAllocation", pulp.LpMaximize)

    # x[s,o] = 1 if slab s assigned to order o
    x = {
        (s, o): pulp.LpVariable(f"x_{s}_{o}", cat="Binary")
        for (s, o) in compatible_pairs
    }

    # y[o] = 1 if order o is fulfilled
    y = {
        order.order_id: pulp.LpVariable(f"y_{order.order_id}", cat="Binary")
        for order in orders
    }

    # Large M to prioritise fulfilment over waste minimisation
    M = 1000

    # Objective: maximise priority-weighted fulfilment, minimise waste as tiebreaker
    prob += (
        M * pulp.lpSum(orders_dict[o].priority * y[o] for o in y)
        - pulp.lpSum(
            (slabs_dict[s].length - required_lengths[(s, o)]) * x[(s, o)]
            for (s, o) in compatible_pairs
        )
    )

    # Constraint 1: each slab assigned to at most one order
    for slab in slabs:
        slab_pairs = [(s, o) for (s, o) in compatible_pairs if s == slab.slab_id]
        if slab_pairs:
            prob += pulp.lpSum(x[(s, o)] for (s, o) in slab_pairs) <= 1

    # Constraint 2: each order assigned to at most one slab
    # Constraint 3: y[o] tied to x assignments
    for order in orders:
        order_pairs = [(s, o) for (s, o) in compatible_pairs if o == order.order_id]
        if order_pairs:
            prob += pulp.lpSum(x[(s, o)] for (s, o) in order_pairs) <= y[order.order_id]
            prob += y[order.order_id] <= pulp.lpSum(x[(s, o)] for (s, o) in order_pairs)
        else:
            prob += y[order.order_id] == 0

    # Solve
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    solve_time = round(time.time() - start_time, 4)

    # Parse results
    allocations = []
    allocated_order_ids = set()

    for (s, o), var in x.items():
        if pulp.value(var) is not None and round(pulp.value(var)) == 1:
            slab = slabs_dict[s]
            order = orders_dict[o]
            req = required_lengths[(s, o)]
            waste = slab.length - req
            allocations.append(AllocationResult(
                order_id=o,
                slab_id=s,
                allocated_length=req,
                waste=waste,
                plates=[p.plate_id for p in order.plates],
                feasible=True
            ))
            allocated_order_ids.add(o)

    # Identify infeasible orders and reason
    infeasible = []
    for order in orders:
        if order.order_id not in allocated_order_ids:
            compatible_slabs = [s for s in slabs if is_compatible(s, order)]
            if not compatible_slabs:
                reason = "No compatible slab found (grade/quality/customer mismatch)"
            elif all(calculate_required_length(s, order) > s.length for s in compatible_slabs):
                reason = "No slab has sufficient length for this order"
            else:
                reason = "All compatible slabs already allocated to higher-priority orders"

            infeasible.append(AllocationResult(
                order_id=order.order_id,
                slab_id="",
                allocated_length=0,
                waste=0,
                plates=[p.plate_id for p in order.plates],
                feasible=False,
                reason=reason
            ))

    total_allocated = sum(a.allocated_length for a in allocations)
    total_slab_used = sum(slabs_dict[a.slab_id].length for a in allocations)
    total_waste = sum(a.waste for a in allocations)
    utilisation = (total_allocated / total_slab_used * 100) if total_slab_used > 0 else 0.0

    return AllocationPlan(
        allocations=allocations,
        infeasible_orders=infeasible,
        total_waste=total_waste,
        utilisation_pct=round(utilisation, 2),
        solve_time_seconds=solve_time
    )
