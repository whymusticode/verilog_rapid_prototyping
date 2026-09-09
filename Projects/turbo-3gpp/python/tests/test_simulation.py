import os
os.environ.setdefault('MPLBACKEND','Agg')
os.environ.setdefault('MPLCONFIGDIR','/tmp/turbo-matplotlib')
import tempfile
import unittest
import numpy as np
import matplotlib.pyplot as plt
import turbo_3gpp as t
from turbo_3gpp.simulation import _parameters
from oracle import Oracle


class TapeRNG:
    def __init__(self, uniforms, normals):
        self.uniforms, self.normals = uniforms, normals
        self.ui = self.ni = 0

    def random(self,n):
        result = self.uniforms[self.ui:self.ui+n]
        self.ui += n
        assert len(result) == n, 'Uniform replay tape exhausted'
        return result

    def standard_normal(self,n):
        result = self.normals[self.ni:self.ni+n]
        self.ni += n
        assert len(result) == n, 'Gaussian replay tape exhausted'
        return result


class SimulationTests(unittest.TestCase):
    def test_both_plot_drivers_against_octave_with_identical_random_samples(self):
        rng = np.random.default_rng(int(os.environ.get('FUZZ_SEED','20260909'))+2)
        for name in ['plot_BLER_vs_SNR','plot_SNR_vs_A']:
            for i in range(4):
                with self.subTest(driver=name,case=i),tempfile.TemporaryDirectory() as output:
                    oracle = Oracle()
                    self.addCleanup(oracle.directory.cleanup)
                    oracle.prepare_plots()
                    A = int(rng.integers(16,80))
                    R = float(rng.choice([.25,.5]))
                    G = int(np.floor(A/R+.5))
                    # Odd G is rounded down by the original Q_m=2 rate rule.
                    G = 2*(G//2)
                    uniforms = rng.random(100000)
                    normals = rng.standard_normal(100000)*1000
                    # Alternate difficult and noiseless channel realizations.
                    for start in range(G,len(normals),2*G):
                        normals[start:start+G] = 0
                    tape = TapeRNG(uniforms,normals)
                    its = np.array([0,.5,1]) if name == 'plot_BLER_vs_SNR' else 1
                    kwargs = dict(A=A,R=R,rv_idx_sequence=(0,),max_iterations=its,
                                  approx_maxstar=bool(i%2),target_block_errors=2,target_BLER=.75,
                                  EsN0_start=-4,EsN0_delta=2,seed=i)
                    py = getattr(t,name)(**kwargs,results_dir=output,rng=tape)[0]
                    # Compare text data, RNG consumption, and a rendered Python image.
                    args = 'A,R,[0],its,approx,2,.75,-4,2,seed'
                    script = f'global uniforms normals ui ni; ui=0; ni=0; {name}({args}); used=[ui,ni];'
                    refs = oracle.run(script,dict(A=A,R=R,its=its,approx=i%2,seed=i,
                                                  uniforms=uniforms,normals=normals),['used'])
                    expected_files = list((oracle.root/'results').glob('*.txt'))
                    self.assertEqual(len(expected_files),1)
                    np.testing.assert_allclose(np.loadtxt(py['file']),np.loadtxt(expected_files[0]),atol=1e-6,rtol=1e-6)
                    np.testing.assert_array_equal([tape.ui,tape.ni],refs[0].ravel())
                    image = os.path.join(output,'plot.png')
                    py['figure'].savefig(image)
                    self.assertGreater(os.path.getsize(image),1000)
                    plt.close('all')

    def test_simulation_parameter_validation(self):
        for args in [(0,.5,[0],1,.1,.5),(40,0,[0],1,.1,.5),
                     (40,.5,[],1,.1,.5),(40,.5,[0],0,.1,.5),
                     (40,.5,[0],1,1,.5),(40,.5,[0],1,.1,0)]:
            with self.assertRaises(ValueError):
                _parameters(*args)
