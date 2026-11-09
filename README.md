# Deep.Meta Slab Allocation System

An intelligent slab-to-order allocation system for steel plate mills, designed to maximise material utilisation and minimise yield loss using Integer Linear Programming (ILP), with LLM-generated natural language summaries for planners.

---

## Context

Deep.Meta's commercial product, SLICE, helps planners select slabs for customer orders through a recommendation-based co-pilot interface. This system takes a complementary approach: rather than recommending one match at a time, it solves the entire allocation problem globally and simultaneously using ILP, guaranteeing the optimal assignment across all slabs and orders in a single planning run.

The `calculate_required_length` stub used here is designed to integrate directly with Deep.Meta's Deep.Optimiser PhyX, which uses real-time furnace sensor data and material science models to compute the precise slab length required for rolling each plate.

---

## Problem Formulation

In a plate mill, steel slabs are reheated and rolled into plates for customer orders. Each order specifies one or more plates with required dimensions, grade, and quality specifications. A planner must allocate available slabs to orders such that:

- Each slab serves at most one order
- Each order is served by at most one slab
- The slab has enough length to produce all plates in the order
- The slab is compatible with the order (grade, quality spec, customer restrictions)
- When slabs are scarce, higher priority orders are served first *(assumed — see Assumptions)*
- Waste within each allocated slab-order pair is minimised

---

## Assumptions

1. **Order priority is not specified in the brief.** Real steel mills operate with varying customer urgency levels (VIP accounts, delivery deadlines, contract penalties). We have added a `priority` field (1=normal, 2=high, 3=urgent) that determines which orders are served first when slabs are scarce. Priority has no effect on waste — waste is determined entirely by how well a slab's length fits the order's requirements, independently for each pair. This field can be removed if all orders are treated equally.

2. **All plates in an order share the same grade and quality specification.**

3. **`calculate_required_length` is additive.** Total slab length required equals the sum of each plate's required length.

4. **Orders must be fulfilled together.** All plates in an order are allocated to the same slab.

5. **Only `available` slabs are eligible.** Reserved and incoming slabs are tracked but not allocated in the current run.

6. **Waste cannot be reused in the current planning horizon.** Remnant tracking is a planned future feature.

---

## Allocation Methodology

### Approach: Integer Linear Programming (ILP)

We use ILP via the PuLP library (CBC solver) to consider all possible slab-order assignments simultaneously and find the globally optimal solution.

### Decision Variables

- `x[s, o]` — binary: 1 if slab `s` is assigned to order `o`
- `y[o]` — binary: 1 if order `o` is fulfilled

### Objective

The objective has two independent concerns:

**1. Fulfilment (who gets a slab):** When slabs are scarce, higher priority orders are served first. Priority only matters when there is not enough inventory for every order.

**2. Waste minimisation (how well each slab fits):** Once a slab is assigned to an order, waste is simply:

```
waste = slab.length - required_length_for_order
```

Each slab-order pair's waste is independent. Slab A's waste has no effect on Slab B's waste. The ILP minimises the sum of all individual wastes across all assignments.

Combined into one objective:

```
Maximise: M × Σ(priority[o] × y[o])  −  Σ(waste[s,o] × x[s,o])
```

`M = 1000` ensures that fulfilling orders always outweighs any waste consideration. Waste minimisation acts as a tiebreaker between otherwise equal solutions.

### Priority Levels

| Value | Label  | Meaning                        |
|-------|--------|--------------------------------|
| 1     | Normal | Standard customer order        |
| 2     | High   | Important customer / deadline  |
| 3     | Urgent | VIP customer / critical order  |

### Constraints

1. Each slab assigned to at most one order
2. Each order assigned to at most one slab
3. `y[o] = 1` only if a slab is assigned to order `o`
4. Only compatible slab-order pairs considered

### Feasibility Reporting

When no allocation is possible, the system explains why:
- No compatible slab (grade/quality/customer mismatch)
- No slab with sufficient length
- All compatible slabs already allocated to higher-priority orders

---

## Project Structure

```
deepmeta_allocation/
├── models/
│   └── models.py           # Slab, Plate, Order, AllocationResult, AllocationPlan
├── services/
│   ├── allocator.py        # Core ILP allocation logic
│   └── llm_summary.py      # LLM-generated planner summaries
├── api/
│   └── main.py             # FastAPI service interface
├── tests/
│   └── test_allocator.py   # Unit tests
├── simulator.py            # Realistic data generator and full pipeline demo
├── requirements.txt
└── README.md
```

---

## Running the Project

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run tests

```bash
python tests/test_allocator.py
```

### Run the simulator (with LLM summaries)

```bash
export GROQ_API_KEY=your_key_here
python simulator.py
```

Get a free Groq API key at: https://console.groq.com

### Run the simulator (without LLM)

```bash
python simulator.py --no-llm
```

### Start the API

```bash
uvicorn api.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API documentation.

---

## Example API Request

```bash
curl -X POST http://localhost:8000/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "slabs": [
      {"slab_id": "S1", "length": 10.0, "grade": "S355", "quality_spec": "standard", "status": "available"}
    ],
    "orders": [
      {
        "order_id": "O1",
        "priority": 2,
        "plates": [
          {"plate_id": "P1", "required_length": 3.0, "grade": "S355", "quality_spec": "standard", "customer_id": "C1"},
          {"plate_id": "P2", "required_length": 4.0, "grade": "S355", "quality_spec": "standard", "customer_id": "C1"}
        ]
      }
    ]
  }'
```

---

## LLM Integration

After the ILP solver runs, the system passes the allocation results to Groq (llama-3.3-70b-versatile) to generate:

1. **A planner-facing operations summary** — overall utilisation, waste, any patterns in failures, and actionable recommendations in plain English
2. **Per-order infeasibility explanations** — when an order fails, the LLM explains why in plain English and suggests a concrete next step for the planner

This mirrors Deep.Meta's philosophy of making AI outputs accessible to operators on the shop floor, not just engineers.

---

## Deployment Strategy

### Containerisation

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Infrastructure

- **Cloud:** AWS ECS or GCP Cloud Run for managed containerised workloads
- **Database:** PostgreSQL for slab inventory and order management
- **Queue:** AWS SQS or RabbitMQ for async allocation jobs on large planning runs

### Scaling Considerations

- ILP is optimal but solve time grows with problem size. For large fleets:
  - **Decompose by grade/quality group** — S355 slabs and orders are independent of S275, so run as separate subproblems (same principle as batching)
  - **Solver time limits** — cap at 30s and return best solution found
  - **Upgrade solver** — swap CBC for Gurobi or CPLEX for 10-100× speed improvement at scale

---

## Monitoring

| Metric | Alert Threshold |
|---|---|
| API latency p95 | > 2s |
| Solver time | > 30s |
| Utilisation % | < 80% |
| Infeasible order rate | > 10% |
| API error rate | > 1% |

### Key Business Metrics

- **Utilisation %** — primary KPI, directly tied to yield loss
- **Infeasible order rate** — high rates signal grade/quality inventory gaps
- **Waste per tonne** — links to commercial yield loss reporting

---

## Future Improvements

- **Remnant tracking** — reuse leftover slab lengths for smaller future orders
- **Order splitting** — fulfil a single order across multiple slabs
- **Rolling physics integration** — replace stub with production Deep.Optimiser PhyX model
- **What-if planning** — lock certain allocations and re-optimise the rest
- **Incoming inventory planning** — pre-allocate incoming slabs to future orders
