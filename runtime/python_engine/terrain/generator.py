
import numpy as np


def generate_terrain(size=30, seed=42):
    """
    Generate a simulated Martian terrain grid.

    Each cell contains:
    - elevation
    - slope
    - roughness
    - hazard level
    - traversability
    """

    rng = np.random.default_rng(seed)

    # Create coordinate grids
    x = np.linspace(-3, 3, size)
    y = np.linspace(-3, 3, size)
    xx, yy = np.meshgrid(x, y)

    # Simulated Martian elevation
    elevation = (
        1000
        + 100 * np.sin(xx)
        + 80 * np.cos(yy)
        + 30 * np.sin(xx * yy)
        + rng.normal(0, 3, (size, size))
    )

    # Calculate slope from elevation
    cell_spacing = 100.0
    dy, dx = np.gradient(elevation,
                         cell_spacing,
                         cell_spacing)
    slope = np.degrees(
    np.arctan(np.sqrt(dx**2 + dy**2))
)
    

    # Estimate surface roughness using local elevation variation
    roughness = np.zeros((size, size))

    for row in range(1, size - 1):
        for col in range(1, size - 1):
            neighbourhood = elevation[
                row - 1:row + 2,
                col - 1:col + 2
            ]
            roughness[row, col] = np.std(neighbourhood)

    # Simulate scattered hazards
    hazard = rng.random((size, size))

    # Mark cells as traversable or impassable
    traversable = (
        (slope < 30)
        & (roughness < 20)
        & (hazard < 0.92)
    )

    return {
        "elevation": elevation,
        "slope": slope,
        "roughness": roughness,
        "hazard": hazard,
        "traversable": traversable
    }


if __name__ == "__main__":
    terrain = generate_terrain()

    print("MARS TERRAIN GENERATED")
    print("Grid size:", terrain["elevation"].shape)
    print("Average elevation:", round(float(np.mean(terrain["elevation"])), 2))
    print("Average slope:", round(float(np.mean(terrain["slope"])), 2))
    print("Traversable cells:", int(np.sum(terrain["traversable"])))
