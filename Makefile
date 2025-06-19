run:
	uv run main.py --loglevel warning
rundbg:
	uv run --with=ipython ipython --pdb --c="%run main.py --loglevel debug"
