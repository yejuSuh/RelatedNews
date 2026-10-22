import matplotlib.pyplot as plt
import numpy as np

sites = ["The Guardian", "CNN", "AP"]

guardian = [10.87, 34.56, 31.79]
cnn = [19.8, 36.89, 27.16]
ap = [18.44, 50.10, 28.73]

data = [guardian, cnn, ap]

averages = [np.mean(site) for site in data]
mins = [np.min(site) for site in data]
maxs = [np.max(site) for site in data]

all_times = guardian + cnn + ap
overall_avg = np.mean(all_times)

lower_errors = [avg - mn for avg, mn in zip(averages, mins)]
upper_errors = [mx - avg for avg, mx in zip(averages, maxs)]
error_bars = [lower_errors, upper_errors]

x = np.arange(len(sites))

plt.figure()
plt.bar(x, averages, yerr=error_bars, capsize=8, label="Per-site average (min–max range)")

plt.axhline(overall_avg, linestyle="--", label=f"Overall avg = {overall_avg:.2f}s")

plt.xticks(x, sites)
plt.xlabel("Site")
plt.ylabel("Pop-Up Latency (s)")
plt.title("Pop-Up Latency for Popular News Sites")
plt.legend()

plt.tight_layout()
plt.savefig("llm.png")
plt.show()

for site, avg, mn, mx in zip(sites, averages, mins, maxs):
    print(f"{site}: avg = {avg:.2f}s, min = {mn:.2f}s, max = {mx:.2f}s")
print(f"\nOverall average across all calls: {overall_avg:.2f}s")
