import os
import time
from codecarbon import OfflineEmissionsTracker

def run_simulation(simulator):
    """Run the Proof of Luck simulation with emissions tracking."""
    # Get the current directory of this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(current_dir, "emissions_outputs")
    os.makedirs(output_dir, exist_ok=True)

    # Configure the emissions tracker
    tracker = OfflineEmissionsTracker(
        country_iso_code="USA",
        measure_power_secs=5,
        log_level="error",
        output_dir=output_dir,
        output_file=f"emissions_{simulator.num_peers}_p_{simulator.min_final_chain_length}_c.csv",
        allow_multiple_runs=False
    )
    tracker.start()

    # Start the simulation
    start_time = time.time()
    simulator.initialize()
    simulator.run()
    end_time = time.time()

    # Format start and end times
    start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
    end_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
    print(f"Simulation started at {start_time_str} and ended at {end_time_str}")

    # Stop the tracker and print emissions data
    tracker.stop()
    print(f"Total energy consumed: {tracker.final_emissions_data.energy_consumed}")
    print(f"Total CPU energy: {tracker.final_emissions_data.cpu_energy}")
    print(f"Total RAM energy: {tracker.final_emissions_data.ram_energy}")
    print(f"Total emissions: {tracker.final_emissions_data.emissions}")
    print(f"CPU power: {tracker.final_emissions_data.cpu_power}")