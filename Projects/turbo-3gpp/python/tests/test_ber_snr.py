"""One end-to-end BER sweep: Python drives independent Python/Octave codecs.

Run from the repository root:
    PYTHONPATH=python python3 -m unittest discover -s python/tests -p test_ber_snr.py -v

Optional environment variables: BER_BLOCKS (default 100), BER_SEED (20260909),
BER_OUTPUT_DIR (default python/results). No MATLAB System-object shim is needed.
"""
import json
import os
from pathlib import Path
import time
import unittest

import numpy as np
import plotly.graph_objects as go

from turbo_3gpp import core
from oracle import Oracle


class BERSweepTest(unittest.TestCase):
    def test_encode_awgn_decode_ber_python_vs_octave(self):
        block_count = int(os.environ.get('BER_BLOCKS', '100'))
        self.assertGreater(block_count, 0)
        seed = int(os.environ.get('BER_SEED', '20260909'))
        K, iterations = 128, 4
        snrs = np.arange(-8., 3., 2.)
        rng = np.random.default_rng(seed)
        payloads = rng.integers(0, 2, (len(snrs), block_count, K)).astype(float)
        # Encoder output has 3*(K+4) bits, including trellis termination.
        noises = rng.standard_normal((len(snrs), block_count, 3*(K+4)))
        output = Path(os.environ.get('BER_OUTPUT_DIR', Path(__file__).resolve().parents[1]/'results'))
        output.mkdir(parents=True, exist_ok=True)
        oracle = Oracle()
        self.addCleanup(oracle.directory.cleanup)
        previous_approx = core.approx_star
        self.addCleanup(setattr, core, 'approx_star', previous_approx)
        core.approx_star = True
        pi = core.internal_interleaver(np.arange(K))
        rows = []
        python_decisions, octave_decisions = [], []
        start = time.monotonic()
        for index, snr in enumerate(snrs):
            point_start = time.monotonic()
            # Unit-energy BPSK: N0 = 1/(Es/N0), real noise variance = N0/2.
            # LLR = log(P(0)/P(1)) = 2*y/sigma^2 = 4*y/N0.
            N0 = 10.**(-snr/10.)
            encoded_python = np.empty((block_count, 3*(K+4)))
            decoded_python = np.empty((block_count, K))
            llrs_python = np.empty_like(encoded_python)
            for block in range(block_count):
                encoded = core.turbo_encoder(payloads[index, block], pi).ravel(order='F')
                received = 1-2*encoded + np.sqrt(N0/2)*noises[index, block]
                llrs = 4*received/N0
                decoded, performed = core.turbo_decoder(llrs.reshape(3,K+4,order='F'), pi, iterations)
                self.assertEqual(performed, iterations)
                encoded_python[block], decoded_python[block], llrs_python[block] = encoded, decoded, llrs
            # Octave independently performs interleaving, encoding, channel
            # simulation and decoding from the same payload/noise arrays.
            script = '''
            approx_star=true;
            pi=internal_interleaver(0:K-1);
            encoded_octave=zeros(size(payload,1),3*(K+4));
            decoded_octave=zeros(size(payload));
            llrs_octave=zeros(size(encoded_octave));
            for block=1:size(payload,1)
                d=turbo_encoder(payload(block,:),pi);
                encoded=reshape(d,1,numel(d));
                received=1-2*encoded+sqrt(N0/2)*noise(block,:);
                llrs=4*received/N0;
                [decoded,performed]=turbo_decoder(reshape(llrs,3,K+4),pi,iterations);
                assert(performed==iterations);
                encoded_octave(block,:)=encoded;
                decoded_octave(block,:)=decoded;
                llrs_octave(block,:)=llrs;
            end
            '''
            encoded_octave, decoded_octave, llrs_octave = oracle.run(
                script, dict(payload=payloads[index],noise=noises[index],K=K,N0=N0,iterations=iterations),
                ['encoded_octave','decoded_octave','llrs_octave'])
            np.testing.assert_array_equal(encoded_python, encoded_octave, err_msg=f'Encoder mismatch at {snr:g} dB')
            np.testing.assert_allclose(llrs_python,llrs_octave,rtol=1e-13,atol=1e-13)
            np.testing.assert_array_equal(decoded_python,decoded_octave,err_msg=f'Decoder mismatch at {snr:g} dB')
            errors_python = int(np.count_nonzero(decoded_python != payloads[index]))
            errors_octave = int(np.count_nonzero(decoded_octave != payloads[index]))
            bits = block_count*K
            rows.append(dict(snr_db=float(snr),bits=bits,python_errors=errors_python,
                             octave_errors=errors_octave,python_ber=errors_python/bits,
                             octave_ber=errors_octave/bits,decoded_bit_mismatches=0,
                             elapsed_seconds=round(time.monotonic()-point_start,3)))
            python_decisions.append(decoded_python)
            octave_decisions.append(decoded_octave)
            print(f'\nEs/N0={snr:5.1f} dB | Python BER={errors_python/bits:.6g} | '
                  f'Octave BER={errors_octave/bits:.6g} | {errors_python}/{bits} errors | exact match',flush=True)
        report = dict(seed=seed,block_bits=K,blocks_per_snr=block_count,iterations=iterations,
                      decoder='max-log-MAP',modulation='BPSK',channel='AWGN',
                      snr_definition='Es/N0 per transmitted coded BPSK symbol',
                      code_rate=K/(3*(K+4)),crc=False,rate_matching=False,
                      same_payloads_and_noise=True,exact_encoder_and_decoder_match=True,
                      total_decoded_bits=int(len(snrs)*block_count*K),
                      elapsed_seconds=round(time.monotonic()-start,3),results=rows)
        (output/'ber_snr_comparison.json').write_text(json.dumps(report,indent=2)+'\n')
        np.savez_compressed(output/'ber_snr_replay.npz',payloads=payloads,standard_normal_noise=noises,
                            snr_db=snrs,python_decisions=python_decisions,octave_decisions=octave_decisions)
        # Zero measured BER cannot be displayed on a logarithmic axis.
        # Place those points at the exact one-sided 95% binomial upper bound.
        zero_bound = -np.expm1(np.log(.05)/(block_count*K))
        fig = go.Figure()
        for implementation,color,symbol,dash in [('python','#55dfff','circle','solid'),
                                                 ('octave','#ffbd69','diamond-open','dash')]:
            rates = [row[f'{implementation}_ber'] for row in rows]
            plotted = [value if value else zero_bound for value in rates]
            details = [[row[f'{implementation}_errors'],row['bits'],value,
                        'Measured BER' if value else 'Zero errors; marker at 95% upper bound']
                       for row,value in zip(rows,rates)]
            fig.add_trace(go.Scatter(x=snrs,y=plotted,name=implementation.title(),mode='lines+markers',
                                    line=dict(color=color,width=3,dash=dash),
                                    marker=dict(symbol=symbol,size=11 if implementation=='python' else 16),
                                    customdata=details,
                                    hovertemplate=('%{x:g} dB<br>BER: %{customdata[2]:.6g}'
                                                   '<br>Errors: %{customdata[0]} / %{customdata[1]}'
                                                   '<br>%{customdata[3]}<extra>%{fullData.name}</extra>')))
        fig.update_layout(template='plotly_dark',title=dict(text='Turbo-code BER · Python vs Octave',x=.04),
                          paper_bgcolor='#0b101b',plot_bgcolor='#101827',font=dict(family='Arial',size=14),
                          xaxis=dict(title='Eₛ/N₀ per coded BPSK symbol (dB)',dtick=2),
                          yaxis=dict(title='Bit error rate (BER)',type='log'),
                          legend=dict(orientation='h',x=0,y=1.13),hovermode='x unified',
                          margin=dict(l=85,r=35,t=125,b=150),height=720,
                          annotations=[dict(x=0,y=-.22,xref='paper',yref='paper',showarrow=False,align='left',
                                            text=f'{block_count:,} blocks × {K} bits per SNR · {iterations} max-log iterations · BPSK + AWGN<br>'
                                                 f'Identical payloads and noise · All encoded and decoded bits match · Seed {seed}<br>'
                                                 'Terminated turbo core, no CRC or rate matching. Coincident curves indicate parity.<br>'
                                                 'Zero-error points show a 95% upper bound; hover for actual error counts.')])
        html = fig.to_html(full_html=True,include_plotlyjs=True,config=dict(responsive=True,displaylogo=False))
        html = html.replace('<head>','<head><title>Turbo BER — Python vs Octave</title>'
                            '<meta name="viewport" content="width=device-width, initial-scale=1">'
                            '<style>html,body{margin:0;background:#0b101b;color:#e5e7eb}</style>',1)
        chart = output/'ber_snr_comparison.html'
        chart.write_text(html)
        self.assertTrue(chart.is_file())
        print(f'\nPlot: {chart}\nReport: {output / "ber_snr_comparison.json"}',flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
