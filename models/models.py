from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SlabStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    INCOMING = "incoming"


@dataclass
class Plate:
    """A single plate within a customer order."""
    plate_id: str
    required_length: float        # metres
    grade: str                    # e.g. "S355", "S275"
    quality_spec: str             # e.g. "standard", "premium"
    customer_id: str


@dataclass
class Order:
    """A customer order containing one or more plates."""
    order_id: str
    plates: list[Plate]
    must_fulfil_together: bool = True   # all plates must come from same slab batch
    priority: int = 1                   # 1=normal, 2=high, 3=urgent

    @property
    def total_required_length(self) -> float:
        return sum(p.required_length for p in self.plates)

    @property
    def grade(self) -> str:
        # Assumption: all plates in an order share the same grade
        return self.plates[0].grade if self.plates else ""

    @property
    def quality_spec(self) -> str:
        return self.plates[0].quality_spec if self.plates else ""


@dataclass
class Slab:
    """A steel slab available for allocation."""
    slab_id: str
    length: float                 # metres
    grade: str                    # must match order grade
    quality_spec: str             # must match order quality spec
    status: SlabStatus = SlabStatus.AVAILABLE
    reserved_for: Optional[str] = None   # order_id if reserved
    customer_restrictions: list[str] = field(default_factory=list)  # restricted customer IDs

    @property
    def is_available(self) -> bool:
        return self.status == SlabStatus.AVAILABLE


@dataclass
class AllocationResult:
    """Result of allocating a slab to an order."""
    order_id: str
    slab_id: str
    allocated_length: float       # total length consumed by plates
    waste: float                  # leftover unused length
    plates: list[str]             # plate IDs allocated
    feasible: bool = True
    reason: Optional[str] = None  # populated if infeasible


@dataclass
class AllocationPlan:
    """Full allocation plan across all orders."""
    allocations: list[AllocationResult]
    infeasible_orders: list[AllocationResult]
    total_waste: float
    utilisation_pct: float        # percentage of slab length actually used
    solve_time_seconds: float = 0.0
