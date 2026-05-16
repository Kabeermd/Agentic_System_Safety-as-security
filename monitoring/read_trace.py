from inspect_ai.log import read_eval_log
import glob
import os

def read_latest_trace(log_dir="./results"):
    """Read and print the latest eval trace."""
    
    logs = glob.glob(os.path.join(log_dir, "*.eval"))
    if not logs:
        print(f"No logs found in {log_dir}")
        return None
    
    latest = max(logs, key=os.path.getmtime)
    print(f"Reading: {os.path.basename(latest)}\n")
    
    log = read_eval_log(latest)
    
    print(f"Model:   {log.eval.model}")
    print(f"Task:    {log.eval.task}")
    print(f"Status:  {log.status}")
    print(f"Samples: {len(log.samples)}")
    
    for sample in log.samples:
        print(f"\n{'='*60}")
        print(f"SAMPLE ID: {sample.id}")
        print(f"{'='*60}")
        
        print(f"\nINPUT (first 300 chars):")
        print(str(sample.input)[:300])
        
        print(f"\nOUTPUT (first 500 chars):")
        print(sample.output.completion[:500])
        
        print(f"\nMESSAGES IN TRACE: {len(sample.messages)}")
        for i, msg in enumerate(sample.messages):
            print(f"\n[Step {i+1}] Role: {msg.role}")
            content = str(msg.content)[:150]
            print(f"Content: {content}")
        
        print(f"\nSCORE: {sample.scores}")
    
    return log

if __name__ == "__main__":
    read_latest_trace()