#!/usr/bin/python3 

from os import system, stat, path
from subprocess import Popen, PIPE
import argparse
import time
import datetime
import re

# Gyromagnetic ratios of common nucleus to obtain 1H NMR frequency from acqus parameters
# NUC and BF
Gyro_ratio_to_1H = { 
  "1H"  : 1.000000 , 
  "13C" : 0.251504 , 
  "15N" : 0.101360 , 
  "14N" : 0.072259 , 
  "2H"  : 0.153501 , 
  "19F" : 0.940714 , 
  "31P" : 0.404793 }

Maximum_NMR_Time = 60*60*24*15 # 15 days in seconds
# All larger values are considures as errors
# Due to chmod on data dir, copy to fat32/back and other operations
# That chnges file modification time

acqus_re_date_start=  re.compile('^##\\$DATE= ([0-9]*)')
acqus_re_two_dollars= re.compile('^\\$\\$')
# $$ 2015-03-12 16:23:18.072 +0300  nmrsu@av800.localdomain 
acqus_re_date_finish= re.compile('^\\$\\$ ([12]\d{3}-\d\d-\d\d \d\d:\d\d:\d\d.\d+ [+-]\d+)')
acqus_re_probe=       re.compile('^##\\$PROBHD= \\<(.*)$')
acqus_re_nuc=         re.compile('^##\\$NUC([1-8])= \\<(.*)\\>$')
acqus_re_bf=          re.compile('^##\\$BF([1-8])= (.*)$')

# Calculates 1H frequency for spectrometer in MHz
# Works Ok if no 1H nucleus used in experiment

def get_1H_MHz(p, nuc_list, bf_list):
  # print(nuc_list,bf_list)
  spect_mhz = None
  for bf, nuc in zip(bf_list, nuc_list):
     if bf and ( nuc in Gyro_ratio_to_1H.keys()):
        mhz = bf/Gyro_ratio_to_1H[nuc] 
        mhz = round(float(mhz))  # Round MHz to  5MHz
        # print(mhz)
        spect_mhz = int(mhz)
  p['Spect_MHz'] = spect_mhz

def get_user_expname(p, acqus_path):
  if acqus_path:
     expno_path = path.dirname(acqus_path)
     if expno_path:
        expname_path = path.dirname(expno_path)
        expname_name = path.basename(expno_path)
        p['Expname'] = expname_name
        if expname_path:
           nmr_path = path.dirname(expname_path)
           if nmr_path:
              user_name = path.basename(nmr_path)
              p['User'] = user_name

def bruker_get_acqus_params(file_acqus):
   P = {}  # Parameters to return 
   P['Start_seconds'] =  None
   P['Start_Year'] =     None
   P['Start_DateTime'] = None
   P['Finish_seconds'] = None
   P['Finish_Year'] =    None
   P['Finish_Time'] =    None
   P['NMR_Total_Time'] = None
   P['Spect_MHz'] =      None
   P['Probe_name'] =     None
   P['User'] =           None
   P['Expname'] =        None
   P['Error'] =          False

   nuc_list =    [ None for i in range(8) ]
   bf_list =     [ None for i in range(8) ]
   two_dollars_flag = False

   with open(file_acqus,'r') as f:
      for line in f:
         two_dollars_match = acqus_re_two_dollars.match(line)
         if two_dollars_match and not two_dollars_flag:
            # date and time is in the first with leading two dollars 
            two_dollars_flag = True 
            date_finish_match = acqus_re_date_finish.match(line)
            if date_finish_match:
               date_finish_string = date_finish_match.group(1)
               try:
                  datetime_finish = datetime.datetime.strptime(date_finish_string, '%Y-%m-%d %H:%M:%S.%f %z')
                  P['Finish_seconds'] = time.mktime(datetime_finish)
                  P['Finish_DateTime'] = time.localtime(P['Finish_seconds'])
                  P['Finish_Year'] =     P['Finish_DateTime'].tm_year

               except ValueError:
                  print("Internal error: could not interpret date \'{}\' in file \'{}\'".
                    format(date_finish_string, acqus_file))
            continue
               
         date_match= acqus_re_date.match(line)
         if date_match:
            #
            #  NMR experiment is started at that time
            #
            P['Start_seconds'] =  float(date_match.group(1))
            P['Start_DateTime'] = time.localtime(P['Start_seconds'])
            P['Start_Year'] =     P['Start_DateTime'].tm_year
            continue

         probe_match= acqus_re_probe.match(line)
         if probe_match:
            #### Examples of probe names:
            # 08>
            # 33>
            # 36>
            # 40:5mmTXIz-gradient(121)>
            # 5 mm BBO BB-1H/D Z-GRD Z325801/0007
            # 5 mm CPTCI 1H-13C/15N/D Z-GRD Z44908/0017
            # 5 mm CPTCI 1H-13C/15N/D Z-GRD Z44909/0052
            # 5 mm CPTXI 1H-13C/15N/D Z-GRD Z44866/0035
            # 5 mm CPTXI 1H-13C/15N/D Z-GRD Z44918/0038
            # 5 mm CPTXO 13C/D-1H/15N Z-GRD Z108641/0002
            # 5 mm DUL 13C-1H/D Z-GRD Z111650/0132
            # 5 mm Multinuclear inverse Z-grad Z8252/0020
            # 5 mm PABBI 1H/D-BB Z-GRD Z814601/0037
            # 5 mm PABBO BB-1H/D Z104273/0002
            # 5 mm PABBO BB-1H/D Z-GRD Z114262/0008
            # 5 mm PABBO BB-1H/D Z-GRD Z863001/0012
            # 5 mm PATXI 1H-13C/15N/D Z-GRD Z550501/0006
            # 5 mm PATXI 1H-13C/15N/D Z-GRD Z550501/0019
            # 5 mm PATXI 1H-13C/D/15N Z-GRD Z563101/0012
            # 5 mm QNP 1H/13C/15N/31P XYZ-grad
            # 5 mm TXI 1H/D-13C/15N Z-GRD Z8168/0161
            #   5mm TXO Z-grad 13C-det Z8644/0001
            probe_name= probe_match.group(1)
            if len(probe_name.split())>=3:
               probe_name= probe_name.split()[2] # PATXI, CPTCI, etc
            P['Probe_name'] = probe_name
            continue

         nuc_match= acqus_re_nuc.match(line)
         if nuc_match:
            channel= int(nuc_match.group(1))
            nucname= nuc_match.group(2)
            if nucname == "off":
               nucname = None
            nuc_list[channel-1] = nucname
            # print("nuc_match {} -- {}", line, nuc_list)
            continue

         bf_match= acqus_re_bf.match(line)
         if bf_match:
            channel= int(bf_match.group(1))
            bf_MHz= bf_match.group(2)
            if bf_MHz == "off":
               bf_MHz = None
            else:
               bf_MHz = float(bf_MHz)
            bf_list[channel-1]= bf_MHz
            # print("bf_match {} -- {}", line, bf_list)
            continue

      get_1H_MHz(P, nuc_list, bf_list)

      acqus_path = path.dirname(path.normpath(file_acqus))
      for fidser in ["fid", "ser"]:
         file_fidser= path.join(acqus_path, fidser)
         if path.isfile(file_fidser):
            #
            # Experiment is finished at the moment of the modification time of 'fid' or
            # 'ser' file in the current directory
            #
            P['Finish_seconds'] =  float(stat(file_fidser).st_mtime)
            P['Finish_DateTime'] = time.localtime(P['Finish_seconds'])
            P['Finish_Year'] =     P['Start_DateTime'].tm_year
            P['NMR_Total_Time']=   P['Finish_seconds'] - P['Start_seconds']
            if P['NMR_Total_Time'] > Maximum_NMR_Time:
#               P['NMR_Total_Time'] = 0
               P['Error'] = True

            break
      
      if P['NMR_Total_Time'] == None:
         P['NMR_Total_Time'] = 0

      # /u/data/ maxim /nmr/ CT3nk   /1/acqus 
      #          User        Expname
      if acqus_path:
         get_user_expname(P, acqus_path)

   return(P)


def scan_nmr_dir(args):
   scan_year = int(args.year)
   find_acqus_cmd="find {} -name acqus".format(args.path)
   out, err = Popen(find_acqus_cmd, shell=True, stdout=PIPE).communicate()
   out = out.strip().decode('UTF-8')
   all_lines = 0
   year_lines = 0
   error_lines = 0
   for acqus in out.splitlines():
      all_lines+= 1
      P = bruker_get_acqus_params(acqus)
      if P['Start_Year'] == scan_year:
         year_lines+= 1
         if P['Error']:
            error_lines+= 1
         if args.verbose:
            try:
               if P['Error']:
                  e = " ERROR, time can\'t be calculated" 
               else:
                  e = ""
               print("{} {:6.0f} sec {}MHz {:<5} {:<15} {:<35} {}{}".
                  format(P['Start_Year'], P['NMR_Total_Time'],
                     P['Spect_MHz'], P['Probe_name'], 
                     P['User'], P['Expname'], acqus, e))
            except:
               print("Exception: {}".format(acqus))

   print("Total {} acqus files found in {}, acquired in {} year".format(year_lines, args.path, scan_year))
   print("Total {} ERROR FILES -- the modification time was changed".format(error_lines))


if __name__ == '__main__':
   parser = argparse.ArgumentParser()
   parser.add_argument("--year", "-y", help='Show stats for that year', type=str)
   parser.add_argument("--path", "-p", help='Get stats for the specified path', type=str, default = "/u/data")
   parser.add_argument("--verbose", "-v", help='Print details about each found experiment', action='store_true')
   args = parser.parse_args()
   scan_nmr_dir(args)
