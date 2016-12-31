# FTIR
A programm to take a spectrum using Michelson Interferometer anywhere you find a suitable detector. We use this setup with a PI stage (112.1DG) and as a detector we use a pyrodetector  which is connected to a scope from TiePie. 
The program is so far is only tested on windows, but should in principal also work on linux

Requirements:
- PiPython: library which is a up to now unofficial python wrapper from PI for their own GCS library available upon request
- LibTiePie: library from TiePie for accessing the scope, just install it as described on the website
- GuiQwt (>=3.0): The libray I use for plotting
- PyQt5: Gui library
- Python >3.5 probably, I haven't tested it with a lower version

Installation:
Up to now there's now setup.py or anything. Just copy the files in a directory of your choice and run FTIR.py file.
