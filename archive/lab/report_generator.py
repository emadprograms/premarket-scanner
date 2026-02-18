import json
import os
import csv

def generate_reports():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(script_dir, "narrative_evaluation_results.json")
    artifact_dir = "/Users/emadarshadalam/.gemini/antigravity/brain/ac3192d7-bcf7-401c-aa02-60ddc3c52dee"
    
    # Save to BOTH artifact dir (for Antigravity) and local folder (for user)
    report_paths = [
        (os.path.join(artifact_dir, "narrative_report.md"), os.path.join(script_dir, "narrative_report.md")),
        (os.path.join(artifact_dir, "narrative_report.csv"), os.path.join(script_dir, "narrative_report.csv")),
        (os.path.join(artifact_dir, "narrative_report.txt"), os.path.join(script_dir, "narrative_report.txt"))
    ]
    
    if not os.path.exists(results_path):
        print(f"Results file not found at {results_path}")
        return

    with open(results_path, "r") as f:
        data = json.load(f)

    # 1. GENERATE CSV (For Promptfoo)
    with open(report_paths[1][0], "w", newline='') as f1, open(report_paths[1][1], "w", newline='') as f2:
        writer1 = csv.writer(f1)
        writer2 = csv.writer(f2)
        for w in [writer1, writer2]:
            w.writerow(["News_Scenario", "Structural_Scenario", "Bias", "Narrative"])
            for item in data:
                w.writerow([
                    item.get("News_Scenario", ""),
                    item.get("Structural_Scenario", ""),
                    item.get("Bias", ""),
                    item.get("Narrative", "")
                ])

    # 2. GENERATE MATRIX DATA
    news_names = sorted(list(set(x["News_Scenario"] for x in data)), key=lambda x: int(x.split(".")[0]))
    struct_names = sorted(list(set(x["Structural_Scenario"] for x in data)), key=lambda x: int(x.split(".")[0]))
    matrix = {(item["News_Scenario"], item["Structural_Scenario"]): item["Bias"] for item in data}

    # 3. GENERATE TXT MATRIX
    with open(report_paths[2][0], "w") as f1, open(report_paths[2][1], "w") as f2:
        for f in [f1, f2]:
            f.write("NARRATIVE INTEGRITY MATRIX (10x10)\n")
            f.write("="*40 + "\n\n")
            header = "News \\ Struct |" + " | ".join([f"S{i:02d}" for i in range(1, 11)]) + "\n"
            f.write(header)
            f.write("-" * len(header) + "\n")
            for n_name in news_names:
                row = f"{n_name.split('.')[0]:<12} |"
                for s_name in struct_names:
                    bias = matrix.get((n_name, s_name), "Err")
                    char = bias[0] if bias not in ["Error", "Err"] else "X"
                    row += f"  {char}  |"
                f.write(row + "\n")
            f.write("\nLegend: B=Bullish, B=Bearish, N=Neutral, V=Volatile, X=Error/Pending\n")

    # 4. GENERATE MD REPORT (Matrix + Success Count)
    success_count = sum(1 for x in data if x.get("Bias") not in ["Error", "Err"])
    report_md = f"# Narrative Integrity Matrix Report\n\nTotal Successful: {success_count}/100\n\n"
    report_md += "| News \\ Struct | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | S10 |\n"
    report_md += "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n"
    
    for n_name in news_names:
        row_str = f"| **{n_name.split('.')[0]}** |"
        for s_name in struct_names:
            bias = matrix.get((n_name, s_name), "Err")
            if bias == "Error": cell = "❌"
            else:
                emoji = "🟢 " if bias == "Bullish" else "🔴 " if bias == "Bearish" else "⚪ " if bias == "Neutral" else "🟡 "
                cell = f"{emoji}{bias[0]}" if bias != "Err" else "Err"
            row_str += f" {cell} |"
        report_md += row_str + "\n"

    with open(report_paths[0][0], "w") as f1, open(report_paths[0][1], "w") as f2:
        f1.write(report_md)
        f2.write(report_md)

    print(f"Reports generated: .md, .csv, .txt in {artifact_dir}")

if __name__ == "__main__":
    generate_reports()
