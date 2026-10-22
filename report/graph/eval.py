import matplotlib.pyplot as plt
import numpy as np

sources = [
    "Google",
    "Wikipedia",
    "Amazon",
    "X",
    "YouTube",
    "Facebook",
    "Reddit",
    "Guardian",
    "CNN",
    "CBS",
]

prox = [
    np.mean([417, 396, 358]),
    np.mean([385, 351, 298]),
    np.mean([797, 705, 715]),
    np.mean([941, 712, 922]),
    np.mean([2310, 2500, 2680]),
    np.mean([454, 393, 321]),
    np.mean([786, 886, 901]),
    np.mean([392, 362, 360]),
    np.mean([476, 456, 424]),
    np.mean([1748, 774, 812]),
]

unprox = [
    np.mean([264, 274, 233]),
    np.mean([192, 170, 164]),
    np.mean([566, 613, 624]),
    np.mean([578, 570, 567]),
    np.mean([2420, 2320, 2310]),
    np.mean([274, 243, 278]),
    np.mean([600, 643, 557]),
    np.mean([256, 198, 184]),
    np.mean([530, 358, 306]),
    np.mean([464, 391, 212]),
]

faster_percent = (np.array(prox) / np.array(unprox)) * 100

x = np.arange(len(sources)) * 0.8
width = 0.35

plt.figure()
plt.bar(x - width / 2, prox, width, label="Proxied")
plt.bar(x + width / 2, unprox, width, label="Unproxied")

for i, source in enumerate(sources):
    print(f"{source}: {faster_percent[i]:.2f}%")
print(f"Average: {np.mean(faster_percent):.2f}%")

plt.xlabel("Source")
plt.ylabel("Average DOMContentLoaded Time")
plt.title("Proxied vs Unproxied Load Time Comparison")
plt.xticks(x, sources, rotation=45, fontsize=8)
plt.legend()

file_path = "eval.png"
plt.savefig(file_path)
