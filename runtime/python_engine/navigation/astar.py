
import heapq
import math
from itertools import count


def heuristic(a, b, minimum_cost=1.0):
    """
    Admissible octile-distance heuristic.

    Assumes 8-directional movement and a minimum
    movement cost of minimum_cost per grid unit.
    """
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])

    diagonal = min(dr, dc)
    straight = max(dr, dc) - diagonal

    return minimum_cost * (
        diagonal * math.sqrt(2) + straight
    )


def calculate_cell_cost(terrain, row, col):
    """Calculate deterministic cost of entering a cell."""

    slope = float(terrain["slope"][row, col])
    roughness = float(terrain["roughness"][row, col])
    hazard = float(terrain["hazard"][row, col])

    slope_factor = slope / 30.0
    roughness_factor = roughness / 20.0
    hazard_factor = hazard

    return (
        1.0
        + 2.0 * slope_factor
        + 1.5 * roughness_factor
        + 3.0 * hazard_factor
    )


def astar(terrain, start, goal):
    """
    Find a minimum-cost route through traversable terrain.

    Coordinates use (row, column).
    Returns (path, total_cost, distance).
    """

    traversable = terrain["traversable"]
    rows, cols = traversable.shape

    for point in (start, goal):
        if not (
            0 <= point[0] < rows
            and 0 <= point[1] < cols
        ):
            raise ValueError(
                "Coordinate is outside the terrain grid."
            )

    if not traversable[start] or not traversable[goal]:
        return None, math.inf, math.inf

    if start == goal:
        return [start], 0.0, 0.0

    frontier = []
    tie_breaker = count()

    heapq.heappush(
        frontier,
        (heuristic(start, goal), next(tie_breaker), start)
    )

    came_from = {}
    cost_so_far = {start: 0.0}
    distance_so_far = {start: 0.0}

    movements = [
        (-1, 0), (1, 0),
        (0, -1), (0, 1),
        (-1, -1), (-1, 1),
        (1, -1), (1, 1)
    ]

    while frontier:
        _, _, current = heapq.heappop(frontier)

        if current == goal:
            break

        for dr, dc in movements:
            nr = current[0] + dr
            nc = current[1] + dc

            if not (0 <= nr < rows and 0 <= nc < cols):
                continue

            neighbour = (nr, nc)

            if not traversable[neighbour]:
                continue

            diagonal = dr != 0 and dc != 0

            # Prevent cutting across blocked corners
            if diagonal:
                if (
                    not traversable[current[0] + dr, current[1]]
                    or not traversable[current[0], current[1] + dc]
                ):
                    continue

            step_distance = math.sqrt(dr**2 + dc**2)

            # Average the cost of the cells at both ends
            current_cost = calculate_cell_cost(
                terrain, current[0], current[1]
            )
            next_cost = calculate_cell_cost(
                terrain, nr, nc
            )

            step_cost = (
                step_distance
                * (current_cost + next_cost)
                / 2.0
            )

            new_cost = cost_so_far[current] + step_cost

            if (
                neighbour not in cost_so_far
                or new_cost < cost_so_far[neighbour]
            ):
                cost_so_far[neighbour] = new_cost

                distance_so_far[neighbour] = (
                    distance_so_far[current] + step_distance
                )

                came_from[neighbour] = current

                priority = (
                    new_cost
                    + heuristic(neighbour, goal)
                )

                heapq.heappush(
                    frontier,
                    (priority, next(tie_breaker), neighbour)
                )

    if goal not in came_from:
        return None, math.inf, math.inf

    path = []
    current = goal

    while current != start:
        path.append(current)
        current = came_from[current]

    path.append(start)
    path.reverse()

    return (
        path,
        cost_so_far[goal],
        distance_so_far[goal]
    )
