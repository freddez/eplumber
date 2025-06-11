run:
	uv run main.py
rundbg:
	uv run --with=ipython ipython --pdb --c="%run main.py"
