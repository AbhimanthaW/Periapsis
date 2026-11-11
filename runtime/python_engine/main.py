
from terrain.generator import generate_terrain
from navigation.astar import astar
from analysis.suitability import plot_terrain


def main():
    print("=" * 45)
    print("       NASA MARS ROVER NAVIGATION")
    print("=" * 45)

    terrain = generate_terrain(size=30, seed=42)

    start = (0, 0)
    intended_goal = (29, 29)

    print("\nGenerating terrain...")
    print("Grid dimensions:", terrain["elevation"].shape)
    print("Traversable cells:", int(terrain["traversable"].sum()))

    if not terrain["traversable"][start]:
        print("MISSION ABORTED: Start is unsafe.")
        return

    # Find reachable cells using breadth-first search
    rows, cols = terrain["traversable"].shape
    reachable = {start}
    queue = [start]

    movements = [
        (-1, 0), (1, 0),
        (0, -1), (0, 1),
        (-1, -1), (-1, 1),
        (1, -1), (1, 1)
    ]

    while queue:
        current = queue.pop(0)

        for dr, dc in movements:
            nr = current[0] + dr
            nc = current[1] + dc

            if not (0 <= nr < rows and 0 <= nc < cols):
                continue

            neighbour = (nr, nc)

            if neighbour in reachable:
                continue

            if not terrain["traversable"][neighbour]:
                continue

            if dr != 0 and dc != 0:
                if not terrain["traversable"][current[0] + dr, current[1]]:
                    continue
                if not terrain["traversable"][current[0], current[1] + dc]:
                    continue

            reachable.add(neighbour)
            queue.append(neighbour)

    print("\nReachable cells:", len(reachable))

    if not reachable:
        print("No reachable terrain found.")
        return

    # Select the closest reachable destination
    goal = min(
        reachable,
        key=lambda point: (
            (point[0] - intended_goal[0]) ** 2
            + (point[1] - intended_goal[1]) ** 2
        )
    )

    goal = (int(goal[0]), int(goal[1]))

    print("Starting position:", start)
    print("Selected destination:", goal)

    # Calculate route
    print("\nCalculating rover route...")

    path, cost, distance = astar(terrain, start, goal)

    if path is None:
        print("No traversable route found.")
        return

    print("\nROUTE FOUND")
    print("-" * 35)
    print("Route steps:", len(path))
    print("Grid distance:", round(distance, 2))
    print("Navigation cost:", round(cost, 2))

    print("\nOpening terrain visualisation...")

    plot_terrain(
        terrain,
        path=path,
        start=start,
        goal=goal
    )


if __name__ == "__main__":
    main()
