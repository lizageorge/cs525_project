import os
import argparse
import re
import csv
import datetime

NUM_PEERS = [ 30 ]
NUM_BLOCKS = [5, 10]
# NUM_BLOCKS = [5, 10, 50]


def extract_simulation_data(output_text):
    """Extract runtime and timestamp data from simulation output."""
    data = {}
    
    # Extract runtime
    runtime_match = re.search(r"Ran for (\d+\.\d+) seconds", output_text)
    if runtime_match:
        data['runtime'] = float(runtime_match.group(1))
    
    # Extract start and end times
    time_match = re.search(r"Simulation started at (\S+ \S+) and ended at (\S+ \S+)", output_text)
    if time_match:
        data['start_time'] = time_match.group(1)
        data['end_time'] = time_match.group(2)
    
    data['peers_in_sync'] = "All peers are in sync!" in output_text
    data['blockchains_match'] = "All blockchains match till minimum heights!" in output_text

     # Extract energy and emissions data
    energy_match = re.search(r"Total energy consumed: ([\d\.e\-]+)", output_text)
    if energy_match:
        data['total_energy'] = float(energy_match.group(1))
    
    cpu_energy_match = re.search(r"Total CPU energy: ([\d\.e\-]+)", output_text)
    if cpu_energy_match:
        data['cpu_energy'] = float(cpu_energy_match.group(1))
    
    ram_energy_match = re.search(r"Total RAM energy: ([\d\.e\-]+)", output_text)
    if ram_energy_match:
        data['ram_energy'] = float(ram_energy_match.group(1))
    
    emissions_match = re.search(r"Total emissions: ([\d\.e\-]+)", output_text)
    if emissions_match:
        data['emissions'] = float(emissions_match.group(1))
    
    power_match = re.search(r"CPU power: ([\d\.e\-]+)", output_text)
    if power_match:
        data['cpu_power'] = float(power_match.group(1))
    
    
    return data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the specified simulation X times per configuration.")
    parser.add_argument(
        "--num_runs", type=int, required=True, help="Number of times to run the simulation per config"
    )
    parser.add_argument(
        "--sim",
        type=str,
        required=True,
        help="Directory to the consensus algo to simulate",
    )

    args = parser.parse_args()

    sim_name = args.sim.split("/")[-1]
    if sim_name == "":
        sim_name = args.sim.split("/")[-2]
    print(f"Running simulations for {sim_name}")
    OUTPUT_DIR = os.path.join("results", f"{sim_name}")
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    csv_path = os.path.join(OUTPUT_DIR, f"{sim_name}_results.csv")
    with open(csv_path, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Run', 'Num Peers', 'Chain Length', 'Runtime', 'Interval Start', 'Interval End', 'Total Energy (kWh)', 'CPU Energy (kWh)', 'RAM Energy (kWh)', 'Total Emissions (CO2 Kg)', 'Avg CPU Power (W)', 'Peers In Sync', 'Blockchains Match'])
    
    for num_peers in NUM_PEERS:
        for num_blocks in NUM_BLOCKS:
            avg_of_runs = {
                'runtime': [],
                'total_energy': [],
                'cpu_energy': [],
                'ram_energy': [],
                'emissions': [],
                'cpu_power': []
            }
            for run in range(args.num_runs):
                run_num = run + 1
                print(f"Running {args.sim} simulation with {num_peers} peers for {num_blocks} blocks, run {run_num}")
                
                # Create unique filename for this run
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"{OUTPUT_DIR}/run_{num_peers}peers_{num_blocks}blocks_{run_num}_{timestamp}.txt"
                
                # Run the simulation and capture output
                command = f"python3 {args.sim}/simulation.py --num_peers {num_peers} --min_final_chain_length {num_blocks}"
                stream = os.popen(command)
                output = stream.read()
                
                with open(output_filename, 'w') as f:
                    f.write(output)
                
                data = extract_simulation_data(output)
                
                if 'runtime' in data and 'start_time' in data and 'end_time' in data:
                    with open(csv_path, 'a', newline='') as csvfile:
                        csv_writer = csv.writer(csvfile)
                        csv_writer.writerow([
                            run_num,
                            num_peers,
                            num_blocks,
                            data['runtime'],
                            data['start_time'],
                            data['end_time'],
                            data.get('total_energy', 'N/A'),
                            data.get('cpu_energy', 'N/A'),
                            data.get('ram_energy', 'N/A'),
                            data.get('emissions', 'N/A'),
                            data.get('cpu_power', 'N/A'),
                            data['peers_in_sync'],
                            data['blockchains_match']
                        ])
                    
                    avg_of_runs['runtime'].append(data['runtime'])
                    if 'total_energy' in data:
                        avg_of_runs['total_energy'].append(data['total_energy'])
                    if 'cpu_energy' in data:
                        avg_of_runs['cpu_energy'].append(data['cpu_energy'])
                    if 'ram_energy' in data:
                        avg_of_runs['ram_energy'].append(data['ram_energy'])
                    if 'emissions' in data:
                        avg_of_runs['emissions'].append(data['emissions'])
                    if 'cpu_power' in data:
                        avg_of_runs['cpu_power'].append(data['cpu_power'])

                    print(f"Run {run_num} completed: Runtime {data['runtime']} seconds, results saved to {output_filename}")
                else:
                    print(f"Warning: Couldn't extract all required data from run {run_num}")
            
            # add a row that is the avg of all the runs
            with open(csv_path, 'a', newline='') as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow([
                    "Average",
                    num_peers,
                    num_blocks,
                    sum(avg_of_runs['runtime']) / len(avg_of_runs['runtime']),
                    "N/A",
                    "N/A",
                    sum(avg_of_runs['total_energy']) / len(avg_of_runs['total_energy']) if avg_of_runs['total_energy'] else 'N/A',
                    sum(avg_of_runs['cpu_energy']) / len(avg_of_runs['cpu_energy']) if avg_of_runs['cpu_energy'] else 'N/A',
                    sum(avg_of_runs['ram_energy']) / len(avg_of_runs['ram_energy']) if avg_of_runs['ram_energy'] else 'N/A',
                    sum(avg_of_runs['emissions']) / len(avg_of_runs['emissions']) if avg_of_runs['emissions'] else 'N/A',
                    sum(avg_of_runs['cpu_power']) / len(avg_of_runs['cpu_power']) if avg_of_runs['cpu_power'] else 'N/A',
                    "N/A",
                    "N/A"
                ])
            

    
    print(f"All simulations completed. Results saved to {csv_path}")
