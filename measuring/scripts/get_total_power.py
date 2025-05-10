"""
Not actually used in final experiments, keeping just in case
"""
import os
import argparse
import pandas as pd

MEASURE_INTERVAL = 15


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sim",
        type=str,
        required=True,
        help="Directory to the consensus algo to simulate",
    )
    args = parser.parse_args()

    simulation_dir = os.path.join(args.sim, "emissions.csv")
    if not os.path.exists(simulation_dir):
        raise FileNotFoundError(f"Simulation directory {simulation_dir} does not exist.")
    sim_name = args.sim.split("/")[-1]

    df = pd.read_csv(simulation_dir)

    required_columns = ["emissions", "cpu_power", "ram_power", "cpu_energy", "ram_energy", "energy_consumed"]
    filtered_df = df[required_columns]

    summed_values = filtered_df.sum() * MEASURE_INTERVAL

    # Write the results to {sim_name}_emissions.out
    output_file = f"{sim_name}_emissions.out"
    with open(output_file, "w") as out_file:
        for column, value in summed_values.items():
            out_file.write(f"{column}: {value}\n")

    print(f"Summed values written to {output_file}")
