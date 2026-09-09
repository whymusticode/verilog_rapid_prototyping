"""Execute original .m functions; adapt only System-object plumbing for Octave."""
from pathlib import Path
import subprocess
import tempfile
from collections import Counter
import numpy as np
from scipy.io import savemat, loadmat

MATLAB = Path(__file__).resolve().parents[2] / 'turbo-3gpp-matlab'


def cell(values):
    out = np.empty((1,len(values)), dtype=object)
    for i, value in enumerate(values):
        out[0,i] = value
    return out


def matlab_value(value):
    # MATLAB callers use doubles. Integer MAT values change Octave division,
    # rounding and even mixed-type arithmetic, invalidating the oracle.
    if isinstance(value, np.ndarray) and value.dtype == object:
        out = np.empty(value.shape, dtype=object)
        for index in np.ndindex(value.shape):
            out[index] = matlab_value(value[index])
        return out
    if isinstance(value, str):
        return value
    array = np.asarray(value, dtype=float)
    # A Python empty vector is a MATLAB 1x0 row, not a 0x0 matrix.
    # scipy.io otherwise erases that distinction for empty 1-D arrays.
    return array.reshape(1, -1) if array.ndim == 1 else array


class Oracle:
    comparisons = Counter()
    processes = 0

    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='turbo-octave-')
        self.root = Path(self.directory.name)
        # Preserve all algorithm bodies; replace unavailable matlab.System
        # plumbing and the upstream decoder's misnamed constructor only.
        for name in ('turbo_coding_chain','turbo_encoding_chain','turbo_decoding_chain'):
            src = (MATLAB / (name+'.m')).read_text(errors='replace')
            src = src.replace('matlab.System','handle').replace('Access = protected','Access = public')
            src = src.replace('function obj = NRLDPCDecoder(', 'function obj = turbo_decoding_chain(')
            src = src.replace('setProperties(obj,nargin,varargin{:});',
                              'for ii=1:2:length(varargin), obj.(varargin{ii}) = varargin{ii+1}; end')
            (self.root / (name+'.m')).write_text(src)

    def run(self, script, inputs, names):
        Oracle.processes += 1
        savemat(self.root/'in.mat', {k: matlab_value(v) for k,v in inputs.items()}, oned_as='row')
        quote = lambda p: str(p).replace("'", "''")
        full = (f"addpath('{quote(MATLAB)}'); addpath('{quote(self.root)}','-begin'); "
                f"load('{quote(self.root/'in.mat')}'); global approx_star; approx_star=false;\n" + script +
                f"\nsave('-mat7-binary','{quote(self.root/'out.mat')}',"+
                ','.join("'"+n+"'" for n in names)+');')
        (self.root/'run_case.m').write_text(full)
        result = subprocess.run(['octave','--quiet','--no-gui',str(self.root/'run_case.m')],
                                capture_output=True,text=True,timeout=180,cwd=self.root)
        if result.returncode:
            raise AssertionError(result.stdout+'\n'+result.stderr+'\n'+script)
        out = loadmat(self.root/'out.mat')
        return [out[n] for n in names]

    def batch(self, name, cases, outputs=1, approximate=False):
        Oracle.comparisons[name] += len(cases)
        inputs = {'cases': cell([cell(args) for args in cases])}
        lhs = ','.join(f'o{j}' for j in range(outputs))
        script = f'approx_star={int(approximate)}; result=cell(length(cases),{outputs});\n'
        script += f'for i=1:length(cases), args=cases{{i}}; [{lhs}]={name}(args{{:}});\n'
        script += ''.join(f'result{{i,{j+1}}}=o{j}; ' for j in range(outputs))+'end;'
        return self.run(script, inputs, ['result'])[0]

    def prepare_plots(self):
        """Headless graphics stubs plus explicit random-sample replay.

        Neither the simulation loops nor channel/decoder math are rewritten.
        Graphics handles are placeholders because this Octave has no toolkit.
        """
        import re
        (self.root/'results').mkdir(exist_ok=True)
        for name in ['figure','axes','title','ylabel','xlabel','ylim','hold','drawnow',
                     'plot','legend','set','grid','xlim']:
            output = '[0,100]' if name == 'xlim' else '1'
            (self.root/(name+'.m')).write_text(f'function x={name}(varargin)\nx={output};\nend\n')
        (self.root/'rng.m').write_text('function rng(varargin)\nend\n')
        for name,tape,index in [('rand','uniforms','ui'),('randn','normals','ni')]:
            (self.root/(name+'.m')).write_text(f'''function x={name}(varargin)
global {tape} {index};
if length(varargin)==1, dims=varargin{{1}}; else dims=[varargin{{:}}]; end
n=prod(dims); x=reshape({tape}({index}+1:{index}+n),dims); {index}={index}+n;
end
''')
        for name in ['plot_BLER_vs_SNR','plot_SNR_vs_A']:
            src = (MATLAB/(name+'.m')).read_text(errors='replace')
            src = re.sub(r'(hEnc = turbo_encoding_chain\([^;]+;)',r'\1 hEnc.setupImpl();',src)
            src = re.sub(r'(hDec = turbo_decoding_chain\([^;]+;)',r'\1 hDec.setupImpl();',src)
            src = src.replace('reset(hDec);','hDec.resetImpl();')
            src = src.replace('f = hEnc(a);','hEnc.processTunedPropertiesImpl(); hDec.processTunedPropertiesImpl(); f = hEnc.stepImpl(a);')
            src = src.replace('hDec(f_tilde)','hDec.stepImpl(f_tilde)')
            (self.root/(name+'.m')).write_text(src)
