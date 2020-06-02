#!/usr/bin/env python
'''
Description:	Opens and continuously updates ds9 with the latest guider file

History:		Jan 21, 2011	Jon Brinkmann	Apache Point Observatory
				Created file from spds9.py

Notes:			Uses the latest SJD
'''
from dircache import listdir
from ds9 import *
from optparse import OptionParser
from os import getpid, path, stat
from stat import ST_MTIME
from time import sleep, time

verbose = False

def sjd () :
	'''Calculate SDSS Modified Julian Date (SJD)'''

	TAI_UTC = 34	# TAI-UTC = 34 seconds as of 1/1/09
	return int ((time() + TAI_UTC) / 86400.0 + 40587.3)

class gds9 :
	'''Displays the last image from the guider camera in ds9'''

	def __init__ (self, fits_dir='', target='', scale='histequ', zoom='fit') :

#	Constants and variables

		self.last_file = ''

#	Arguments

		if fits_dir :
			self.dir = fits_dir
		else :
			self.dir = '/data/gcam/%s' % sjd()

		if target :
			self.target = target
		else :
			self.target = 'gds9.%s' % getpid()

		self.scale = scale
		self.zoom = zoom

		if verbose :
			print('dir = %s\ntarget = %s\nscale = %s\nzoom = %s' % \
				(self.dir, self.target, self.scale, self.zoom))

#	Initialize

		self.ds9 = ds9 (self.target)

	def is_fits (self, filename) :
		'''Returns whether a file is a FITS file based on its extension'''

		length = len (filename)
		if filename.rfind ('.fit') == (length - 4) or \
				filename.rfind ('.fits') == (length - 5) or \
				filename.rfind ('.fit.gz') == (length - 7) or \
				filename.rfind ('.fits.gz') == (length - 8) :
			return True
		else :
			return False

	def latest_fits_file (self, pattern) :
		'''Returns the latest FITS file matching <pattern>'''

		max_time = -1
		fits_filename = ''

#	Obtain the files in the directory and add the full path to them

		for file in listdir (self.dir) :
			file = path.join (self.dir, file)

#	See if the file name matches the pattern and the file is a FITS file

			if (file.find (pattern) > 0) and self.is_fits (file) :
#				print max_time, file, mtime

#	Store the name and mtime of only the latest FITS file

				mtime = stat (file)[ST_MTIME]
				if max_time < mtime :
					fits_filename = file
					max_time = mtime

		return fits_filename
#		return sorted (fits_files.items(), key=lambda (k,v): (v,k), reverse=True)[0][0]

	def display (self, file, frame) :
		'''Display <file> in <frame> with optional scaling and zoom'''

		if frame >= 0 and file != '' :
			self.ds9.set ('frame %s' % frame)
			self.ds9.set ('file %s' % file)

			if zoom :
				self.ds9.set ('zoom to %s' % self.zoom)

			if scale :
				self.ds9.set ('scale %s' % self.scale)

	def update (self) :
		'''Update the display'''

		file = self.latest_fits_file ('gimg')
		if verbose :
			print('latest fits file = %s, last fits file = %s' % (file, self.last_file))

		if file != self.last_file :
			if verbose :
				print('displaying %s' % file)
			self.display (file, 0)
			self.last_file = file

# If run as a program, start here

if __name__ == '__main__' :

#	Define command line options

	parser = OptionParser (version="%prog 1.0")
	parser.add_option ('-d', '--directory', dest='fits_dir', default=None,
		type='string', help='Set FITS data directory. Default is /data/gcam/<SJD>')
	parser.add_option ('-t', '--target', dest='target', default=None,
		type='string', help='Set ds9 target. Default is autogenerated.')
	parser.add_option('-a', '--autoupdate', action='store_true', dest='auto_mjd',
		default=False, help='Auto update SJD.  Default is False.')
	parser.add_option ('-i', '--interval', dest='interval', default=5,
		type='int', help='Set the refresh rate.	Default is 5 seconds. \
			Refreshes will be this number of seconds apart.')
	parser.add_option ('-s', '--scale', dest='scale', default='histequ',
		type='string', help='Set scaling. Default is "histequ"')
	parser.add_option('-v', '--verbose', action='store_true', dest='verbose',
		default=False, help='Be verbose.  Default is to be quiet.')
	parser.add_option ('-z', '--zoom', dest='zoom', default='1.0',
		type='string', help='Set zoom factor. Default is 1.0')

#	Get command line options

	(options, args) = parser.parse_args()
     
	fits_dir = options.fits_dir
	target = options.target
	auto_mjd = options.auto_mjd
	interval = int (options.interval)
	scale = options.scale
	verbose = options.verbose
	zoom = options.zoom

	if verbose :
		print('auto_mjd = %d' % auto_mjd)
		print('interval = %d' % interval)
		print('scale = %s' % scale)
		print('zoom = %s' % zoom)

#	Start the display

	if auto_mjd :
		old_sjd = 0
	else :
		g = gds9 (fits_dir, target, scale, zoom)

	while (True) :
		if auto_mjd and (old_sjd != sjd()) :
			try :
				print(stat ('/data/gcam/%d' % sjd())[ST_MTIME])

				if verbose :
					print('Setting SJD from %d to %d' % (old_sjd, sjd()))
				old_sjd = sjd()

				g = gds9 (None, target, scale, zoom)
				g.update()

			except :
				if verbose :
					print('No files for SJD %d, retrying...' % sjd())
#				sleep (interval)
#				next
		else :
			g.update()

		sleep (interval)
