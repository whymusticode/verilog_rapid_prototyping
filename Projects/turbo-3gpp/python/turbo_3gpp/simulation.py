"""QPSK/AWGN Monte Carlo plots corresponding to the two MATLAB drivers.

SPDX-License-Identifier: GPL-3.0-or-later
Python and MATLAB RNGs differ. Supply an RNG exposing random(n) and
standard_normal(n) to replay identical random samples across runtimes.
"""
from pathlib import Path
import numpy as np
from . import core
from .chains import turbo_encoding_chain, turbo_decoding_chain


def _transmit(A, enc, dec, rvs, N0, rng):
    a = np.floor(rng.random(A)+0.5)
    dec.reset()
    ahat, its = np.array([]), np.array([0.])
    for rv in rvs:
        enc.rv_idx = int(rv)
        dec.rv_idx = int(rv)
        f = enc(a)
        f2 = np.r_[f,np.zeros((-len(f)) % 2)]
        tx = np.sqrt(.5)*(2*f2[::2]-1)+1j*np.sqrt(.5)*(2*f2[1::2]-1)
        rx = tx+np.sqrt(N0/2)*(rng.standard_normal(len(tx))+1j*rng.standard_normal(len(tx)))
        llr = np.empty(len(f2))
        llr[::2] = -4*np.sqrt(.5)*rx.real/N0
        llr[1::2] = -4*np.sqrt(.5)*rx.imag/N0
        ahat, its = dec(llr[:len(f)])
        if len(ahat):
            break
    return np.array_equal(a,ahat), its


def _parameters(A, R, rv_idx_sequence, target_block_errors, target_BLER, EsN0_delta):
    A, R = np.atleast_1d(A).astype(int), np.atleast_1d(R).astype(float)
    if np.any(A <= 0) or np.any(R <= 0) or not len(rv_idx_sequence):
        raise ValueError('A, R and the redundancy sequence must be nonempty and positive')
    if target_block_errors < 1 or not 0 < target_BLER < 1 or EsN0_delta <= 0:
        raise ValueError('Require positive error target/SNR step and 0 < target_BLER < 1')
    return A,R


def plot_BLER_vs_SNR(A=40, R=40/132, rv_idx_sequence=(0,),
                     max_iterations=tuple(np.arange(0,8.5,.5)), approx_maxstar=True,
                     target_block_errors=10, target_BLER=1e-3, EsN0_start=-10,
                     EsN0_delta=.5, seed=0, *, results_dir='results', rng=None):
    """Run the original stopping rule, save TSV results and return curves/figures.

    Like the MATLAB driver, this may run for a long time for small target BLER.
    Each returned dict contains A, R, SNR, block/error counts, figure and file.
    """
    import matplotlib.pyplot as plt
    A,R = _parameters(A,R,rv_idx_sequence,target_block_errors,target_BLER,EsN0_delta)
    rng = np.random.default_rng(seed) if rng is None else rng
    core.approx_star = bool(approx_maxstar)
    iterations = np.unique(np.atleast_1d(max_iterations))
    root = Path(results_dir)
    root.mkdir(parents=True,exist_ok=True)
    results = []
    for rate in R:
        for size in A:
            fig, ax = plt.subplots()
            ax.set(yscale='log',ylim=(target_BLER,1),xlabel=r'$E_s/N_0$ [dB]',ylabel='BLER',
                   title=f'3GPP LTE Turbo code, A = {size}, R = {rate:g}, RVs = {len(rv_idx_sequence)}, approx = {int(approx_maxstar)}, QPSK, AWGN, errors = {target_block_errors}')
            lines = [ax.plot([],[],label=f'{it:.1f} its')[0] for it in iterations]
            ax.legend(loc='lower left')
            G = int(np.floor(size/rate+.5))
            enc = turbo_encoding_chain(A=int(size),G=G,Q_m=2)
            dec = turbo_decoding_chain(A=int(size),G=G,Q_m=2,I_HARQ=1,iterations=max(iterations))
            counts, errors, snrs = [], [], []
            filename = root/f'BLER_vs_SNR_{size}_{rate:g}_{len(rv_idx_sequence)}_{int(approx_maxstar)}_{target_block_errors}_{EsN0_start:g}_{seed}.txt'
            bler, snr, found_start = 1., EsN0_start, False
            with filename.open('w') as out:
                out.write('#Es/N0\tBLER after iteration\n#dB'+''.join(f'\t{it:.1f}' for it in iterations)+'\n')
                while bler > target_BLER:
                    counts.append(0); errors.append(np.zeros(len(iterations))); snrs.append(snr)
                    keep_going = True
                    while keep_going and errors[-1][-1] < target_block_errors:
                        success, performed = _transmit(int(size),enc,dec,rv_idx_sequence,10**(-snr/10),rng)
                        if not found_start and not success:
                            keep_going, bler = False, 1.
                        else:
                            found_start = True
                            if not success:
                                errors[-1] += 1
                            else:
                                if len(performed) != 1:
                                    raise ValueError('The source plotting driver requires a single code block')
                                errors[-1][iterations < performed[0]] += 1
                            counts[-1] += 1
                            bler = errors[-1][-1]/counts[-1]
                    if bler < 1:
                        out.write(f'{snr:f}'+''.join(f'\t{e/counts[-1]:e}' for e in errors[-1])+'\n')
                    snr += EsN0_delta
            with np.errstate(invalid='ignore',divide='ignore'):
                curves = np.array(errors).T/np.array(counts)
            for line, curve in zip(lines,curves):
                line.set_data(snrs,curve)
            ax.relim(); ax.autoscale_view(scaley=False)
            results.append(dict(A=int(size),R=float(rate),SNR=np.array(snrs),
                                block_counts=np.array(counts),block_error_counts=np.array(errors).T,
                                BLER=curves,figure=fig,file=filename))
    return results


def plot_SNR_vs_A(A=(40,50), R=(1/2,1/3), rv_idx_sequence=(0,), max_iterations=8,
                  approx_maxstar=True, target_block_errors=10, target_BLER=.1,
                  EsN0_start=-10, EsN0_delta=.5, seed=0, *, results_dir='results', rng=None):
    """Estimate required SNR by the source's log-BLER interpolation rule."""
    import matplotlib.pyplot as plt
    A,R = _parameters(A,R,rv_idx_sequence,target_block_errors,target_BLER,EsN0_delta)
    rng = np.random.default_rng(seed) if rng is None else rng
    core.approx_star = bool(approx_maxstar)
    root = Path(results_dir); root.mkdir(parents=True,exist_ok=True)
    fig, ax = plt.subplots()
    ax.set(xlabel='A',ylabel=r'Required $E_s/N_0$ [dB]',
           title=f'3GPP LTE Turbo code, iterations = {max_iterations:g}, RVs = {len(rv_idx_sequence)}, approx = {int(approx_maxstar)}, QPSK, AWGN, errors = {target_block_errors}')
    ax.grid(True)
    results = []
    for rate in R:
        snrs = np.full(len(A),np.nan)
        filename = root/f'SNR_vs_A_{target_BLER:g}_{rate:g}_{max_iterations:g}_{target_block_errors}_{seed}.txt'
        with filename.open('w') as out:
            for index,size in enumerate(A):
                G = int(np.floor(size/rate+.5))
                enc = turbo_encoding_chain(A=int(size),G=G,Q_m=2)
                dec = turbo_decoding_chain(A=int(size),G=G,Q_m=2,I_HARQ=1,iterations=max_iterations)
                found_start, bler, snr = False, 1., EsN0_start-EsN0_delta
                while bler > target_BLER:
                    prev_snr = snr
                    snr += EsN0_delta
                    error_count = block_count = 0
                    keep_going = True
                    while keep_going and error_count < target_block_errors:
                        success, _ = _transmit(int(size),enc,dec,rv_idx_sequence,10**(-snr/10),rng)
                        if not found_start and not success:
                            keep_going, error_count, block_count = False, 1, 1
                        else:
                            found_start = True
                            error_count += int(not success)
                            block_count += 1
                    prev_bler, bler = bler, error_count/block_count
                snrs[index] = np.interp(np.log10(target_BLER),np.log10([bler,prev_bler]),[snr,prev_snr])
                out.write(f'{size:d}\t{snrs[index]:f}\n')
        ax.plot(A,snrs,label=f'R={rate:.2f}')
        results.append(dict(A=A.copy(),R=float(rate),SNR=snrs,figure=fig,file=filename))
    ax.legend(loc='center left',bbox_to_anchor=(1, .5))
    return results
