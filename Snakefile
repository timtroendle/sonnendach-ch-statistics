CONFIG_FILE = "config/default.yaml"

configfile: CONFIG_FILE
include: "rules/sonnendach.smk"
include: "rules/sync.smk"

localrules: all, clean

onstart:
    shell("mkdir -p build/logs")
onsuccess:
    if "email" in config.keys():
        shell("echo "" | mail -s 'sonnendach-ch-statistics succeeded' {config[email]}")
onerror:
    if "email" in config.keys():
        shell("echo "" | mail -s 'sonnendach-ch-statistics crashed' {config[email]}")


rule all:
    input:
        "build/total-rooftop-area-km2.txt",
        "build/total-yield-twh.txt",
        "build/roof-statistics.csv",


rule clean: # removes all generated results
    shell:
        """
        rm -r ./build/*
        echo "Data downloaded to data/ has not been cleaned."
        """
