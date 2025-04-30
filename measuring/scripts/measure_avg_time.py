import os
import argparse
import re
import csv
import datetime

# NUM_PEERS = [10, 30, 50, 100]
# NUM_BLOCKS = [5, 10, 50]


NUM_PEERS = [10, 30]
NUM_BLOCKS = [5, 10]

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

    OUTPUT_DIR = os.path.join("results", f"{args.sim.split('/')[-1]}")
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    csv_path = os.path.join(OUTPUT_DIR, f"{args.sim.split('/')[-1]}_results.csv")
    with open(csv_path, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(['Run', 'Num Peers', 'Chain Length', 'Runtime', 'Interval Start', 'Interval End', 'Peers In Sync', 'Blockchains Match'])
    
    for num_peers in NUM_PEERS:
        for num_blocks in NUM_BLOCKS:
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
                            data['peers_in_sync'],
                            data['blockchains_match']
                        ])
                    
                    print(f"Run {run_num} completed: Runtime {data['runtime']} seconds, results saved to {output_filename}")
                else:
                    print(f"Warning: Couldn't extract all required data from run {run_num}")
    
    print(f"All simulations completed. Results saved to {csv_path}")