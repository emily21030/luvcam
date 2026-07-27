from datetime import datetime, timezone
import re
from luvcam.vis import ra_dec_to_quaternion, hms_to_deg, dms_to_deg

'''
notes / todo:
- calibration img does not need aocs stuff --- create separate function?

- dt_pointing / dt_detumble: add option for dt in minutes or specific time in UTC

- add search for ra/deg for known objects?

- tests

- GRBBeta will/will not be illuminated by the Sun.

- GRBBeta lon,lat

- always put at least 1 sec between two mcr items

- create commands for data download (luvcam img + temp measurement)

- create commands for deleting luvcam + temp files (once downloaded!)

- documentation

'''

def _string_to_hex(s):
    '''
    Takes a string (number will be converted to string) and returns it decoded in the format for "data" part in mcr commands. 
    Format only relevant for luvcam commands (cli 1 "luvcam ...").
    '''
    decoded_string = ""
    for ch in str(s):
        decoded_string += hex(ord(ch))[2:].upper()
        decoded_string += " "
    decoded_string = re.sub(r'\s+', ' ', decoded_string).strip() # remove trailing and internal spaces
    return decoded_string

def _get_luvcam_expose_data(img_filename,img_exp,img_x_offset,img_y_offset,img_xs,img_ys,img_gain=0):
    '''
    Creates "data" part for mcr command that takes luvcam image.
    Format:
    # "luvcam expose <filename>.raw <exp_ms> 0 <x> <y> <xs> <ys>"
    '''
    space = " 20 "
    luvcam_expose = "6C 75 76 63 61 6D 20 65 78 70 6F 73 65"

    img_filename = img_filename.strip()
    if ".raw" in img_filename:
        filename = _string_to_hex(img_filename)
    else:
        filename = _string_to_hex(img_filename)
        filename += ' '
        filename += _string_to_hex(".raw")

    exp = _string_to_hex(img_exp)
    gain = _string_to_hex(img_gain)

    x_offset = _string_to_hex(img_x_offset)
    y_offset = _string_to_hex(img_y_offset)

    xs = _string_to_hex(img_xs)
    ys = _string_to_hex(img_ys)

    data = luvcam_expose + space + filename + space + exp + space + gain + space + x_offset + space + y_offset + space + xs + space + ys + " 00"
    data = re.sub(r'\s+', ' ', data).strip()
    return data


def create_op_plan_science_img(img_time_utc,target_ra,target_dec,
                               img_filename,img_exp,
                               dt_pointing=20,target_name=None,flush_img_filename='noise',
                               output_fn='op_plan'):
    '''
    This function creates an operation plan for AOCS+LUVCam operation.

    required arguments:
    - img_time_utc: UTC time when the image should be taken, e.g. 2026-04-22 20:35:00 
    - target_ra: right ascension of the target as a float in degrees or tuple in format (hour,minute,second)
    - target_dec: declination of the target as a float in degrees or tuple in format (degree,arcminute,arcsecond)
    - img_filename: name of the luvcam image, e.g. 26d22a
    - img_exp: required exposure in miliseconds, e.g. 1000 (= 1s)
    - img_type: "science" or "calibration"
            "science": 1000x1000px image centered to the illuminated part of CMOS
            "calibration": 512x512px image from a specific part of the non-illuminated part of CMOS
            For images in SAA use "calibration".

    optional arguments:
    - dt_pointing: how many minutes before the image is taken should pointing begin (default: 20 min)
    - target_name: this is just for your information and clarity, e.g. Pleiades
    - flush_img_filename: name of the flush image (default: noise)
    - output_fn: name of the output txt file, by default "op_plan.txt"

    output:
    - .txt file with the operation plan to be executed
    '''

    # define slot number
    slot = 4 
    # define source node for mcr commands
    source = 28
    # limit for times the command should be sent
    attempts = 30

    # convert ra,dec if needed
    if (type(target_ra) == tuple) and (len(target_ra)==3):
        ra_deg = hms_to_deg(target_ra[0],target_ra[1],target_ra[2])
    elif (type(target_ra) == float):
        ra_deg = target_ra
    else:
        raise ValueError("Format of target RA is incorrect. Needs to be float in degrees or tuple in format (hour,minute,second).")

    if (type(target_dec) == tuple) and (len(target_dec)==3):
        dec_deg = dms_to_deg(target_dec[0],target_dec[1],target_dec[2])
    elif (type(target_dec) == float):
        dec_deg = target_dec
    else:
        raise ValueError("Format of target Dec is incorrect. Needs to be float in degrees or tuple in format (degree,arcminute,arcsecond).")

    # quaternion components
    q0,q1,q2,q3 = ra_dec_to_quaternion(ra_deg,dec_deg)

    # define img size and sensor coords
    img_x_offset=1548
    img_y_offset=2846
    img_xs=1000
    img_ys=1000

    # timestamp of luvcam image and others
    dt = datetime.strptime(img_time_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    ts_img = int(dt.timestamp())
    ts_pointing = int(ts_img-dt_pointing*60)

    ts_detumbling = int(ts_pointing-35*60)

    if ts_img-ts_pointing<0:
        raise ValueError("Pointing cannot begin after the image is taken!")

    if ts_pointing-ts_detumbling<0:
        raise ValueError("Pointing cannot begin before detumbling!")

    # create "data" part from mcr command from the input parameters
    luvcam_expose_data = _get_luvcam_expose_data(img_filename,img_exp,img_x_offset,img_y_offset,img_xs,img_ys)

    # create "data" part from mcr command for flush img
    flush_luvcam_expose_data = _get_luvcam_expose_data(flush_img_filename,img_exp=10,img_x_offset=1548,img_y_offset=2846,img_xs=256,img_ys=256)

    # how many seconds before the real image should the flush img be taken 
    dt_flush = 4*60
    # if flush img op will end after the real img begins, raise error
    if int(ts_img-dt_flush+2*60) > int(ts_img-45):
        raise ValueError("Flush image is too close to the real image, increase dt for flush image.")
    # if temp measurement begins later than the flush img, raise error
    if int(ts_img-301) > int(ts_img-dt_flush-45):
        raise ValueError("Temperature measurement begins later than the flush image, decrease dt for flush image.")

    # img filename format for drops
    flush_img_filename = flush_img_filename.split('.')[0]

    # img filename format for drops
    filename = img_filename.split('.')[0]

    # target name syntax
    if target_name == None:
        target_name = "a target"

    op_plan = f"""# This is an operation plan for LUVCam image of {target_name} 
# at RA = {ra_deg} deg, Dec = {dec_deg} deg at {img_time_utc} UTC
# with an exposure of {img_exp/1000} seconds.
# Verify that the target will not be behind the Earth.

# Detumbling will begin at {datetime.fromtimestamp(ts_detumbling,tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}.
# Pointing will begin at {datetime.fromtimestamp(ts_pointing,tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}, 
# {dt_pointing} minutes before the image will be taken. Verify that 
# the satellite will be illuminated by the Sun.

# MAKE SURE THE TIMES ARE LATER THAN THE PASS WHEN YOU EXECUTE THE COMMANDS.

# Below follows a list of commands to be executed (for now manually by an operator).
# The commands should be executed in this order.

# Check housekeeping data, expecially that PSU channels are on and 
# battery voltage is not low (e.g. <7.95V)
psu hk

# 1. 
# Wipe datakeeper (DK) = AOCS data
# Make sure previous data were downloaded or are not needed.
dk wipe 10 1
dk wipe 10 13
dk wipe 10 41
dk wipe 10 43
dk wipe 10 44
dk wipe 10 50

# check DK storage
dk list
dk st  
    
# 2. 
# TLE upload 
# Updated file "TLE.txt" needs to be in your home directory on 10.42.1.53. 
# You can download it by following command, then upload it 
# to 10.42.1.53 via FTP (e.g. Midnight Commander in linux): 
# curl 'https://celestrak.org/NORAD/elements/gp.php?CATNR=60237&FORMAT=TLE' | tail -n2 > TLE.txt  
vac pos tle TLE.txt
vac pos fetch
vac pos sat

# 3. 
# Define target and verify it is correctly set
vac g ss 0
vac g sq -- {q0},{q1},{q2},{q3} ECI {slot}
vac g ss {slot}
vac g gs
vac g gt {slot}

# 4. 
# Disable pointing (we first need to spin down the satellite)
per set tc_safe2obs 0
per ls tc_safe2obs

# 5.
# schedule detumbling to begin 20 minutes before pointing for 1 hour
# first we delete all current items from the minicron planner
cli 14 "mcrr a"
# following command will start detumbling ("upy run 4 -a1800") 20 minutes before pointing
cli 14 "mcra {ts_detumbling} 1 1 {source} 10 26 33 0 TRX 00 04 08 07 00 00 00 00 00 00 00 00 00 00 00 00"

# 6. 
# schedule pointing to begin {dt_pointing} minutes before the image is taken
# the pointing will last 40 minutes 
# following command will execute "per set tc_safe2obs 1200" at the specified time
cli 14 "mcra {ts_pointing} 1 1 {source} 10 19 34 0 TRX 01 74 63 5F 73 61 66 65 32 6F 62 73 00 00 00 00 00 00 00 00 00 00 00 00 01 B0 04 00 00"

# 7.
# following two commands will begin temperature measurement 
# 5 min before the image for 10 min
# the measurement will be saved in "dtsol6.b" file on node 6
cli 14 "mcra {int(ts_img-305)} 1 1 {source} 6 8 35 0 TRX 00 1C 0C 98 6E 16 00 64 74 73 6F 6C 36 2E 62"
cli 14 "mcra {int(ts_img-301)} 1 1 {source} 6 16 36 0 TRX 14 00 00 00 00 00 00 00 05 00 00 00 6F 00 78 00 00 8C C5 B8 00"

# 8. 
# LUVCam op:
# following 5 commands will take the flush image XX min before the real image
# (256x256px, 10ms exposure, just to read out noise, this won't be downloaded)
cli 14 "mcra {int(ts_img-dt_flush-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00"
cli 14 "mcra {int(ts_img-dt_flush-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" 
cli 14 "mcra {ts_img-dt_flush} 1 1 {source} 1 7 39 0 TRX {flush_luvcam_expose_data}"
cli 14 "mcra {int(ts_img-dt_flush+60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00"
cli 14 "mcra {int(ts_img-dt_flush+2*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00"

# following 5 commands will turn on LUVCam, take the image and turn off LUVCam
cli 14 "mcra {int(ts_img-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00"
cli 14 "mcra {int(ts_img-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" 
cli 14 "mcra {ts_img} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data}"
cli 14 "mcra {int(ts_img+2*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00"
cli 14 "mcra {int(ts_img+3*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00"

# 9. 
# check items saved in minicron scheduler
# this is mainly for debuging in case something goes wrong
# there should be 14 items
cli 14 mcr

# This is the end of the main operation.

# After the image is taken, it is necessary to download following data:
# - LUVCam image
# - temperature measurement
# - AOCS data

# ALWAYS VERIFY THAT DATA IS DOWNLOADED BEFORE DELETING ANYTHING.

# AOCS data can be downloaded by a robot. Check email for more info.

# Temperature measurement takes 20 seconds to download, 
# so it can be done during an interactive pass:
grb address_offset 6
grb getf 0 -u -i -1 -w 8 -p 200 dtsol6.b -n 100

# Science LUVCam image (1000x1000 px) typically needs 8 passes to download.
# The drops can be either started manually at the beginning of each pass,
# or, more conveniently, they can be scheduled for later passes via minicron.
# The exact minicron commands will be implemented in later version of this tool.
# For now, you can get the minicron commands in the SatOp after you log to 10.42.1.53.
# Before each "grb getf" command, change time to that of the pass when you want 
# it to be downloaded. Each part should be downloaded during different pass.

# part 1/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 0 -s 250112 -n 3000

# part 2/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 250112 -s 250112 -n 3000

# part 3/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 500224 -s 250112 -n 3000

# part 4/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 750336 -s 250112 -n 3000

# part 5/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 1000448 -s 250112 -n 3000

# part 6/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 1250560 -s 250112 -n 3000

# part 7/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 1500672 -s 250112 -n 3000

# part 8/8
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 1750784 -s 249344 -n 3000


# Example:
# We want to download part of 26d10a.raw file during pass which begins 
# at 2026-04-11 17:06:00 UTC. Copy following two lines to SatOp:

2026-04-11 17:06:00
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 26d10a.raw -f 0 -s 250112 -n 3000

# You will get following output:

Timestamp: 1775927160

# CSP [PACKET] OUT: S 28, D 1, Dp 16, Sp 33, Pr 2, Fl 0x00, Sz 41 VIA: LOOP (1) data: 18 31 C7 67 28 FF F8 00 0C 00 00 00 C8 00 00 00 00 00 00 00 00 00 03 D1 00 80 00 0B B8 32 36 64 31 30 61 2E 72 61 77 00 2D
cli 14 "mcra 1775927160 1 1 28 1 16 33 0 TRX 18 31 C7 67 28 FF F8 00 0C 00 00 00 C8 00 00 00 00 00 00 00 00 00 03 D1 00 80 00 0B B8 32 36 64 31 30 61 2E 72 61 77 00 2D"
# Regex: Cron|OK|Error

# The "cli 14 ..." command is the (only) one that 
# we send to the satellite:

cli 14 "mcra 1775927160 1 1 28 1 16 33 0 TRX 18 31 C7 67 28 FF F8 00 0C 00 00 00 C8 00 00 00 00 00 00 00 00 00 03 D1 00 80 00 0B B8 32 36 64 31 30 61 2E 72 61 77 00 2D"

# Typically, it is not necessary to download the flush image.
# However, in case we need it, here is the command for download:

YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {flush_img_filename}.raw -n 1500

# After all files are successfully downloaded, we delete them:
cli 1 "rm {filename}.raw {flush_img_filename}.raw"
grb sh 0 rm dtsol6.b


# This is the end of the full operation plan. Thank you for your service!
"""

    with open(f"{output_fn}.txt", "w") as file:
        file.write(op_plan)    

    op_plan_satop = f"""# Below follows a list of commands to be copied into SatOp.
# The commands should be executed in this order.

a dk wipe 10 1  # wiped|err # {attempts}
a dk wipe 10 13 # wiped|err # {attempts}
a dk wipe 10 41 # wiped|err # {attempts}
a dk wipe 10 43 # wiped|err # {attempts}
a dk wipe 10 44 # wiped|err # {attempts}
a dk wipe 10 50 # wiped|err # {attempts}
a dk list # \-\\r?\\n[^a-z]*$ # {attempts}
a dk st # DK # {attempts}
a cli 1 ll # responseLen # {attempts}
a vac pos tle /var/local/lib/vcom/logs/grbbeta/currentpass/TLE.txt # reply # {attempts}
a vac pos fetch # reply # {attempts}
a vac pos sat # reply # {attempts}
a vac g ss 0 # reply # {attempts}
a vac g sq -- {q0},{q1},{q2},{q3} ECI {slot} # reply # {attempts}
a vac g ss {slot} # reply # {attempts}
a vac g gs # reply # {attempts}
a vac g gt {slot} # reply # {attempts}
a cli 14 "mcrr a" # OK # {attempts}
a cli 14 "mcra 10 1 1 28 10 19 37 0 TRX 01 74 63 5F 73 61 66 65 32 6F 62 73 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 00" # OK|Cron|Error # {attempts}
a per ls tc_safe2obs # tc_safe2obs # {attempts}
a per ls tc_safe2obs # tc_safe2obs # 10
a cli 14 "mcra {ts_detumbling} 1 1 {source} 10 26 33 0 TRX 00 04 08 07 00 00 00 00 00 00 00 00 00 00 00 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {ts_pointing} 1 1 {source} 10 19 34 0 TRX 01 74 63 5F 73 61 66 65 32 6F 62 73 00 00 00 00 00 00 00 00 00 00 00 00 01 B0 04 00 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-305)} 1 1 {source} 6 8 35 0 TRX 00 1C 0C 98 6E 16 00 64 74 73 6F 6C 36 2E 62" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-301)} 1 1 {source} 6 16 36 0 TRX 14 00 00 00 00 00 00 00 05 00 00 00 6F 00 78 00 00 8C C5 B8 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-dt_flush-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-dt_flush-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {ts_img-dt_flush} 1 1 {source} 1 7 39 0 TRX {flush_luvcam_expose_data}" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-dt_flush+60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-dt_flush+2*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {ts_img} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data}" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img+2*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00" # OK|Cron|Error # {attempts}
a cli 14 "mcra {int(ts_img+3*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00" # OK|Cron|Error # {attempts}
a cli 14 mcr # OK # {attempts}
a cli 1 ll # responseLen # {attempts} {datetime.fromtimestamp(int(ts_img+4*60),timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
a grb sh 0 ll # .b # {attempts} {datetime.fromtimestamp(int(ts_img+4*60),timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

"""

    with open(f"{output_fn}_satop.txt", "w") as file:
        file.write(op_plan_satop)




def create_op_plan_calibration_img(img_time_utc,img_filename,img_exp,
                                   dt_bg=3,bg_exp=10,
                                   dt_noise=4,noise_exp=1000,
                                   output_fn="op_plan",):
    '''
    This function creates an operation plan for LUVCam only operation. It is useful for calibration and images in SAA.
    Noise image is a small one 256x256px; background image has the same dimensions as science.

    required arguments:
    - img_time_utc: UTC time when the image should be taken, e.g. 2026-04-22 20:35:00 
    - img_filename: name of the luvcam image, e.g. 26d22a
    - img_exp: required exposure in miliseconds, e.g. 1000 (= 1s)

    optional arguments:
    - dt_bg: minutes prior to real image when the background image should be taken; at least 3 min are needed (default: 3 min)
    - bg_exp: exposure of the background image in ms (default: 10ms)
    - dt_noise: minutes prior to bg image when the noise image should be taken; at least 4 min are needed (default: 4 min)
    - noise_exp: exposure of the noise image in ms (default: 1000 = 1s)
    - output_fn: name of the output txt file, by default "op_plan.txt"

    output:
    - .txt file with the operation plan to be executed
    '''

    if dt_bg<3:
        raise ValueError("dt_bg cannot be lower than 3min")
    if dt_noise<4:
        raise ValueError("dt_noise cannot be lower than 4min")

    # define source node for mcr commands
    source = 28


    # define img size and sensor coords
    img_x_offset=1808
    img_y_offset=1119
    img_xs=512
    img_ys=512

    # timestamp of luvcam image and others
    dt = datetime.strptime(img_time_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    ts_img = int(dt.timestamp())

    # create "data" part from mcr command from the input parameters
    luvcam_expose_data = _get_luvcam_expose_data(img_filename,img_exp,img_x_offset,img_y_offset,img_xs,img_ys)

    # img filename format for drops
    filename = img_filename.split('.')[0]

    bg_filename = filename+'b'
    luvcam_expose_data_bg = _get_luvcam_expose_data(bg_filename,bg_exp,img_x_offset,img_y_offset,img_xs,img_ys)
    noise_filename = filename+'n'
    luvcam_expose_data_noise = _get_luvcam_expose_data(noise_filename,noise_exp,int(img_x_offset+128),int(img_y_offset+128),256,256)


    op_plan = f"""# This is an operation plan for LUVCam image
# of the non-illuminated part of CMOS at {img_time_utc} UTC
# with an exposure of {img_exp/1000} seconds.

# A {bg_exp}ms background image will be taken {dt_bg} minutes before the science image.
# A {noise_exp}ms background image will be taken {dt_noise} minutes before the background image.

# MAKE SURE THE TIME IS LATER THAN THE PASS WHEN YOU EXECUTE THE COMMANDS.

# Below follows a list of commands to be executed (for now manually by an operator).
# The commands should be executed in this order.

# 0.
# remove old temperature file
# make sure it was already downloaded
# this may not be performed; the data will just append to the existing file in the worst case 
grb sh 0 rm dtsol6.b

# delete all cron items
cli 14 "mcrr a"

# 1.
# Schedule temperature measurement starting 2 min before the noise image and lasting 20 min.
# The measurement will be saved in "dtsol6.b" file on node 6.
cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-5*60)} 1 1 {source} 6 8 35 0 TRX 00 1C 0C 98 6E 16 00 64 74 73 6F 6C 36 2E 62"
cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-2*60)} 1 1 {source} 6 16 36 0 TRX 14 00 00 00 00 00 00 00 05 00 00 00 6F 00 F0 00 00 8C C5 B8 00"

# 2a. 
# LUVCam op:
# following 5 commands will turn on LUVCam, take a noise image and turn off LUVCam
cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00"
cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" 
cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60)} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data_noise}"
cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60+2*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00"
cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60+3*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00"

# 2b. 
# LUVCam op:
# following 5 commands will turn on LUVCam, take a background image and turn off LUVCam
cli 14 "mcra {int(ts_img-dt_bg*60-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00"
cli 14 "mcra {int(ts_img-dt_bg*60-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" 
cli 14 "mcra {int(ts_img-dt_bg*60)} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data_bg}"
cli 14 "mcra {int(ts_img-dt_bg*60+1.5*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00"
cli 14 "mcra {int(ts_img-dt_bg*60+2*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00"

# 2c. 
# LUVCam op:
# following 5 commands will turn on LUVCam, take the science image and turn off LUVCam
cli 14 "mcra {int(ts_img-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00"
cli 14 "mcra {int(ts_img-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" 
cli 14 "mcra {ts_img} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data}"
cli 14 "mcra {int(ts_img+2*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00"
cli 14 "mcra {int(ts_img+3*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00"

# 3. 
# check items saved in minicron scheduler
# this is mainly for debuging in case something goes wrong
# there should be 17 items
cli 14 mcr

# This is the end of the main operation.

# After the image is taken, it is necessary to download following data:
# - LUVCam image
# - temperature measurement

# ALWAYS VERIFY THAT DATA IS DOWNLOADED BEFORE DELETING ANYTHING.

# Temperature measurement takes 20 seconds to download, 
# so it can be done during an interactive pass:
grb address_offset 6
grb getf 0 -u -i -1 -w 8 -p 200 dtsol6.b -n 100

# potentially also scheduled with other drops (e.g., after one of the longer ones during high and long passes)
YYYY-MM-DD HH:MM:SS
m grb getf 0 -u -i -1 -w 8 -p 200 dtsol6.b -n 100

# Calibration LUVCam image (512x512 px) typically needs 2 passes to download.
# The drops can be either started manually at the beginning of each pass,
# or, more conveniently, they can be scheduled for later passes via minicron.
# The exact minicron commands will be implemented in later version of this tool.
# For now, you can get the minicron commands in the SatOp after you log to 10.42.1.53.
# Before each "grb getf" command, change time to that of the pass when you want 
# it to be downloaded. Each part should be downloaded during different pass.

## science image
# part 1/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 0 -s 262144 -n 3000

# part 2/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 262144 -s 262272 -n 3000

## background image
# part 1/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {bg_filename}.raw -f 0 -s 262144 -n 3000

# part 2/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {bg_filename}.raw -f 262144 -s 262272 -n 3000

## noise image
# part 1/1
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {noise_filename}.raw -n 1500


# Example:
# We want to download part of 26d10a.raw file during pass which begins 
# at 2026-04-11 17:06:00 UTC. Copy following two lines to SatOp:

2026-04-11 17:06:00
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 26d10a.raw -f 0 -s 250112 -n 3000

# You will get following output:

Timestamp: 1775927160

# CSP [PACKET] OUT: S 28, D 7, Dp 16, Sp 59, Pr 2, Fl 0x00, Sz 41 VIA: LOOP (7) data: 18 31 C7 67 28 FF F8 00 0C 00 00 00 C8 00 00 00 00 00 00 00 00 00 03 D1 00 80 00 0B B8 32 36 64 31 30 61 2E 72 61 77 00 2D
cli 14 "mcra 1775927160 1 1 28 1 16 59 0 TRX 18 31 C7 67 28 FF F8 00 0C 00 00 00 C8 00 00 00 00 00 00 00 00 00 03 D1 00 80 00 0B B8 32 36 64 31 30 61 2E 72 61 77 00 2D"
# Regex: Cron|OK|Error

# The "cli 14 ..." command is what we need. Thus the (only) command that we send 
# to the satellite will be:

cli 14 "mcra 1775927160 1 1 28 1 16 59 0 TRX 18 31 C7 67 28 FF F8 00 0C 00 00 00 C8 00 00 00 00 00 00 00 00 00 03 D1 00 80 00 0B B8 32 36 64 31 30 61 2E 72 61 77 00 2D"

# After all files are successfully downloaded, we delete them:
cli 1 "rm {filename}.raw {bg_filename}.raw {noise_filename}.raw"
grb sh 0 rm dtsol6.b


# This is the end of the full operation plan. Thank you for your service!
"""

    with open(f"{output_fn}.txt", "w") as file:
        file.write(op_plan)


    op_plan_satop = f"""# Below follows a list of commands to be copied into SatOp.
# The commands should be executed in this order.

a grb sh 0 rm dtsol6.b # E4|.b
a cli 1 ll # responseLen
a grb sh 0 df # fatfs
a cli 14 "mcrr a" # OK
a cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-5*60)} 1 1 {source} 6 8 35 0 TRX 00 1C 0C 98 6E 16 00 64 74 73 6F 6C 36 2E 62" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-2*60)} 1 1 {source} 6 16 36 0 TRX 14 00 00 00 00 00 00 00 05 00 00 00 6F 00 F0 00 00 8C C5 B8 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60)} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data_noise}" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60+2*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-dt_noise*60+3*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60)} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data_bg}" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60+1.5*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-dt_bg*60+2*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-45)} 1 1 {source} 1 7 37 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 6E 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img-15)} 1 1 {source} 1 7 38 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 6E 00" # OK|Cron|Error
a cli 14 "mcra {ts_img} 1 1 {source} 1 7 39 0 TRX {luvcam_expose_data}" # OK|Cron|Error
a cli 14 "mcra {int(ts_img+2*60)} 1 2 {source} 1 7 40 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 73 65 6E 73 6F 72 20 6F 66 66 00" # OK|Cron|Error
a cli 14 "mcra {int(ts_img+3*60)} 1 2 {source} 1 7 41 0 TRX 6C 75 76 63 61 6D 20 70 6F 77 65 72 20 66 70 67 61 20 6F 66 66 00" # OK|Cron|Error
a cli 14 mcr # OK
a cli 1 ll # responseLen # 30 {datetime.fromtimestamp(int(ts_img+4*60),timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
a grb sh 0 ll # .b # 30 {datetime.fromtimestamp(int(ts_img+4*60),timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


---------------------------------------------------------------------------------
## commands for drops ... the cron commands still need to be retrieved from satop
YYYY-MM-DD HH:MM:SS
m grb getf 0 -u -i -1 -w 8 -p 200 dtsol6.b -n 100

## science image
# part 1/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 0 -s 262144 -n 3000

# part 2/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {filename}.raw -f 262144 -s 262272 -n 3000

## background image
# part 1/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {bg_filename}.raw -f 0 -s 262144 -n 3000

# part 2/2
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {bg_filename}.raw -f 262144 -s 262272 -n 3000

## noise image
# part 1/1
YYYY-MM-DD HH:MM:SS
m grb address_offset 0 # grb getf 1 -u -i -1 -w 8 -p 200 {noise_filename}.raw -n 1500


"""

    with open(f"{output_fn}_satop.txt", "w") as file:
        file.write(op_plan_satop)


# # create op plan
# create_op_plan_science_img(img_time_utc="2026-06-03 20:00:00",
#                            target_ra=150.4,target_dec=53.1,target_name="target",
#                            img_filename="26f03",img_exp=250,flush_img_filename="flush",
#                            dt_pointing=10,output_fn="op_plan_20260603")