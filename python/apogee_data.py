#!/usr/bin/env python
import argparse
from pathlib import Path
from astropy.time import Time
from scipy.optimize import leastsq
import fitsio
import numpy as np
from bin import epics_fetch


class APOGEERaw:
    """A class to parse raw data from APOGEE. The purpose of collecting this
    raw data is to future-proof things that need these ouptuts in case
    things like sdss.autoscheduler changes, which many libraries depend on. This
    will hopefully help SDSS-V logging"""

    def __init__(self, fil, args, ext=1, ):
        self.file = Path(fil)
        self.ext = ext
        self.args = args
        header = fitsio.read_header(fil, ext=ext)
        self.telemetry = epics_fetch.telemetry
        dithers = self.telemetry.get('25m:apogee:ditherNamedPositions',
                                     start=(Time.now() - 1 / 24 / 60 * 5).isot,
                                     end=Time.now().isot,
                                     scan_archives=False, interpolation='raw')
        # layer = self.image[layer_ind]
        # An A dither is DITHPIX=12.994, a B dither is DITHPIX=13.499
        if (header['DITHPIX'] - dithers.values[-1][0]) < 0.05:
            self.dither = 'A'
        elif (header['DITHPIX'] - dithers.values[-1][1]) < 0.05:
            self.dither = 'B'
        else:
            self.dither = '{:.1f}'.format(header['DITHPIX'])
        self.exp_time = header['EXPTIME']
        self.isot = Time(header['DATE-OBS'])  # Local
        self.plate_id = header['PLATEID']
        self.cart_id = header['CARTID']
        self.exp_id = int(str(fil).split('-')[-1].split('.')[0])
        if header['EXPTYPE'].capitalize() == 'Arclamp':
            if header['LAMPUNE']:
                self.exp_type = 'UNe Arc'
            elif header['LAMPTHAR']:
                self.exp_type = 'ThAr Arc'
            else:
                print('Could not process exposure type of {}'.format(self.file))
        else:
            self.exp_type = header['EXPTYPE'].capitalize()
        self.n_read = header['NREAD']
        self.lead = header['PLATETYP']
        self.img_type = header['IMAGETYP'].capitalize()
        if header['EXPTYPE'] == 'OBJECT':
            self.seeing = header['SEEING']
        else:
            self.seeing = 0.0

        self.quickred_data = np.array([[]])
        self.quickred_file = ''

    # noinspection PyTupleAssignmentBalance,PyTypeChecker
    def compute_offset(self, fibers=(30, 35), w0=939, dw=40, sigma=1.2745):
        """This is based off of apogeeThar.OneFileFitting written by Elena. It
        is supposed to generate a float for the pixel offsets of an APOGEE
        ThAr cal. Here is how it works:
        It opens a quickred file, which is of shape n_fiber*n_dispersion_pixels,
        and then it averages the fibers inside the fibers tuple. It then based
        off of the provided w0 (mean) and sigma, it creates a gaussian function
        and then creates a function called err_func that compares the gaussian
        with a slice of the data, from w0-dw/2 to w0+dw/2. It then uses scipy's
        least squared equation solver to find the difference between w0 given as
        an input and the actual w0 of the spectral line. This only works if you
        pick a prominent line to go off of. The default parameters are given for
        ThAr lines, but UNe lines could also be used, with the following inputs:
        fibers: (30, 35)
        w0: 1761
        dw: 20
        sigma: 3
        """
        w0 = int(w0)
        dw = int(dw)
        mjd = self.file.absolute().parent.name
        self.quickred_file = (self.file.absolute().parent.parent.parent
                              / 'quickred/{}/ap1D-a-{}.fits.fz'
                                ''.format(mjd, self.exp_id))
        try:
            if not self.quickred_data:
                self.quickred_data = fitsio.read(self.quickred_file, 1)
        except OSError as e:
            if self.args.verbose:
                print('Offsets for {} produced this error\n{}'.format(self.file,
                                                                      e))
            return np.nan
        lower = w0 - dw // 2
        upper = w0 + dw // 2
        line_inds = np.arange(self.quickred_data.shape[1])[lower:upper]
        line = np.average(self.quickred_data[fibers[0]:fibers[1], lower:upper],
                          axis=0)

        def fit_func(w, x):
            return np.exp(-0.5 * ((x - w) / sigma) ** 2)

        def err_func(w, x, y):
            return fit_func(w, x) - y

        w_model, success = leastsq(err_func, w0, args=(line_inds, line))

        diff = w_model[0] - w0
        return diff

    def ap_test(self, ws=(900, 910), master_col=None, plot=False):
        if master_col is None:
            raise ValueError("APTest didn't receive a valid master_col: {}"
                             "".format(master_col))
        if not self.quickred_data:
            mjd = self.file.absolute().parent.name
            self.quickred_file = (self.file.absolute().parent.parent.parent
                                  / 'quickred/{}/ap1D-a-{}.fits.fz'
                                    ''.format(mjd, self.exp_id))
            try:
                self.quickred_data = fitsio.read(self.quickred_file, 1)
            except OSError as e:
                if self.args.verbose:
                    print('APTest for {} produced this error\n{}'.format(
                        self.file, e))
                return ''
        slc = np.average(self.quickred_data[:, ws[0]:ws[1]], axis=1)
        flux_ratio = slc / master_col
        missing = flux_ratio < 0.2
        faint = (0.2 <= flux_ratio) & (flux_ratio < 0.7)
        bright = ~missing & ~faint
        i_missing = np.where(missing)[0]
        i_faint = np.where(faint)[0]
        i_bright = np.where(bright)[0]
        missing_bundles = self.create_bundles(i_missing)
        faint_bundles = self.create_bundles(i_faint)
        if self.args.verbose:
            print('Missing Fibers: {}'.format(missing_bundles))
            print('Faint Fibers: {}'.format(faint_bundles))
            print()

        if plot:
            import matplotlib.pyplot as plt
            fig = plt.figure(figsize=(9, 4))
            ax = fig.gca()
            x = np.arange(len(flux_ratio)) + 1
            ax.plot(x[i_bright], flux_ratio[i_bright], 'o', c=(0, 0.6, 0.533))
            ax.plot(x[i_faint], flux_ratio[i_faint], 'o', c=(0.933, 0.466, 0.2))
            ax.plot(x[i_missing], flux_ratio[i_missing], 'o',
                    c=(0.8, 0.2, 0.066))
            ax.set_xlabel('Fiber ID')
            ax.set_ylabel('Throughput Efficiency')
            ax.axis([1, 300, -0.2, 1.35])
            ax.grid(True)
            ax.axhline(0.7, c=(0, 0.6, 0.533))
            ax.axhline(0.2, c=(0.933, 0.466, 0.2))
            ax.set_title('APOGEE Fiber Relative Intensity', size=15)
            fig.show()

        return missing_bundles, faint_bundles

    @staticmethod
    def create_bundles(subset):
        # print(subset.shape)
        bundles = [subset]
        b = 0
        for fib in subset:
            if bundles[b].size > 0:
                # print(bundles)
                # print(b)
                # print(bundles[b])
                if bundles[b] + 1 == fib:
                    if fib % 30 == 1:
                        bundles.append(fib)
                        b += 1
                    else:
                        bundles[b] = '{} - {}'.format(
                            bundles[b].split()[0], fib)
                else:
                    bundles.append(fib)
                    b += 1
        for i, bundle in enumerate(bundles):
            if isinstance(bundle, str):
                low, high = np.array(bundle.split(' - ')).astype(int)
                if ((low - 1) // 30) == ((high - 1) // 30):
                    bundles[i] = '{} bundle'.format(low)
        return bundles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--today', action='store_true',
                        help="Whether or not you want to search for today's"
                             " data, whether or not the night is complete."
                             " Note: must be run after 00:00Z")
    parser.add_argument('-m', '--mjd',
                        help='If not today (-t), the mjd to search')
    parser.add_argument('-v', '--verbose', action='count', default=1,
                        help='Show details, can be stacked')
    args = parser.parse_args()
    if args.today:
        mjd_today = int(Time.now().sjd)
        data_dir = '/data/apogee/archive/{}/'.format(mjd_today)
    elif args.mjd:
        data_dir = '/data/apogee/archive/{}/'.format(args.mjd)
    else:
        raise Exception('No date specified')
    print(data_dir)
    for path in Path(data_dir).rglob('apR*.apz'):
        print(path)


if __name__ == '__main__':
    main()
