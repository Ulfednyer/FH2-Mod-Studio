"""Build a car zip with the porter pipeline but WITHOUT the vlayfix step (to see the layouts vlayfix starts from).
usage: prevlay.py <car> <out.zip>"""
import os, shutil, sys
sys.path.insert(0, r"C:\Users\opsuc\Downloads\Anthem_1.0.0.64_x64__8wekyb3d8bbwe\fh2sql\fh3port")
import fh3port
car, out = sys.argv[1], sys.argv[2]
fh3port.fix_vertex_layouts = lambda src, dst, car_name: (shutil.copyfile(src, dst), [])[1]
rc, log, missing = fh3port.convert_zip(os.path.join(fh3port.FH3, "cars", car + ".zip"), car, out)
print("rc", rc, "missing", len(missing))
