# What is it
Tools to generate a 100% map completion, ready to paste into your save

100% vibe coded by Claude

# Usage
Use [sk-zk extractor](https://github.com/sk-zk/Extractor) to extract .base map files from the game like so:
```
extractor PATH_TO_THE_GAME -a -p=/map/usa -f=*.base -d OUTPUT_DIRECTION
```
You can run it again on your `mod` folder if you want.


Then use `scs_base_decode.py` on the `OUTPUT_DIRECTION` to convert .base files from binary data into text format (the same as `edit_save_text` in map editor(almost))

```
python3 scs_base_decode.py OUTPUT_DIRECTION -o BASETXT_DIRECTION
```

Then use `extract_uids.py` to generate the list to paste into the save

```
python3 extract_uids.py -i BASETXT_DIRECTION 
```
You can use it with `--cities` to generate list of cities to unlock.

Paste `combined_output_results.txt` and `cities.txt` into appropiate places in your save.