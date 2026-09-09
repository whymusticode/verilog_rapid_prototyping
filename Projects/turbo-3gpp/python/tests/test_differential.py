"""Seeded differential fuzzing: each public numerical function vs original .m."""
import inspect
import os
import unittest
import numpy as np
import turbo_3gpp as t
from turbo_3gpp import core
from turbo_3gpp._qpp import QPP
from oracle import Oracle, cell


class ComparisonMixin:
    def compare(self, actual, expected):
        if isinstance(actual, (list,tuple)):
            self.assertEqual(len(actual), expected.size)
            for a,b in zip(actual,expected.ravel()):
                self.compare(a,b)
        else:
            a, b = np.asarray(actual), np.asarray(expected)
            if a.ndim < 2:
                b = b.reshape(-1)
                a = a.reshape(-1)
            self.assertEqual(a.shape, b.shape)
            np.testing.assert_allclose(a,b,rtol=2e-11,atol=2e-10,equal_nan=True)


class DifferentialTests(ComparisonMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = Oracle()
        cls.rng = np.random.default_rng(int(os.environ.get('FUZZ_SEED', '20260909')))
        cls.count = int(os.environ.get('FUZZ_CASES', '16'))
        cls.covered = set()

    @classmethod
    def tearDownClass(cls):
        cls.oracle.directory.cleanup()

    def check(self, name, cases, outputs=1, approximate=False):
        self.covered.add(name)
        refs = self.oracle.batch(name, cases, outputs, approximate)
        core.approx_star = approximate
        for i,args in enumerate(cases):
            with self.subTest(function=name,case=i,approximate=approximate):
                python_args = [list(a.ravel()) if isinstance(a,np.ndarray) and a.dtype == object else a for a in args]
                actual = getattr(t,name)(*python_args)
                if outputs == 1:
                    self.compare(actual, refs[i,0])
                else:
                    for j in range(outputs):
                        self.compare(actual[j], refs[i,j])
        core.approx_star = False

    def test_crc_functions(self):
        names = ['CRC24A','CRC24B','CRC16','CRC8']
        self.check('get_3gpp_crc_polynomial',[(name,) for name in names])
        matrices, calc, append, remove = [], [], [], []
        for i in range(self.count):
            n = int(self.rng.integers(0,7000))
            p = t.get_3gpp_crc_polynomial(names[i%4])
            matrices.append((n,p))
            g = t.get_crc_generator_matrix(n,p)
            a = self.rng.integers(0,2,int(self.rng.integers(0,n+1))).astype(float)
            calc.append((a,g)); append.append((a,g))
            b = t.generate_and_append_crc_bits(a,g)
            remove.append((b,g))
            bad = b.copy(); bad[-1] = 1-bad[-1]
            remove.append((bad,g))
        matrices.extend([(0,t.get_3gpp_crc_polynomial('CRC8')),(1,np.array([1,1]))])
        empty_g = t.get_crc_generator_matrix(0,t.get_3gpp_crc_polynomial('CRC8'))
        calc.append((np.array([]),empty_g))
        append.append((np.array([]),empty_g))
        remove.append((np.zeros(8),empty_g))
        self.check('get_crc_generator_matrix',matrices)
        self.check('calculate_crc_bits',calc)
        self.check('generate_and_append_crc_bits',append)
        self.check('check_and_remove_crc_bits',remove)

    def test_lengths(self):
        lengths = [1,39,40,41,511,512,513,1023,1024,1025,2047,2048,2049,6143,6144,6145,12240,12241]
        lengths += self.rng.integers(1,150000,self.count).tolist()
        self.check('get_3gpp_code_block_segment_lengths',[(b,) for b in lengths])
        cases = [(int(self.rng.integers(0,200000)),int(self.rng.integers(1,30)),
                  int(self.rng.integers(1,5)),int(self.rng.choice([1,2,4,6,8,10]))) for _ in range(self.count*3)]
        cases += [(100,3,2,2),(0,1,1,1)]
        self.check('get_3gpp_encoded_code_block_segment_lengths',cases)

    def test_segmentation(self):
        g = t.get_crc_generator_matrix(6144,t.get_3gpp_crc_polynomial('CRC24B'))
        seg, deseg = [], []
        for n in [1,40,41,6144,6145,12240,12241]+self.rng.integers(1,25000,self.count).tolist():
            b = self.rng.integers(0,2,n)
            ks = t.get_3gpp_code_block_segment_lengths(n)
            seg.append((b,ks,g))
            blocks = t.code_block_segmentation(b,ks,g)
            deseg.append((cell([block.copy() for block in blocks]),n,g))
            if len(blocks)>1:
                blocks[-1][-1] = 1-blocks[-1][-1]
                deseg.append((cell([block.copy() for block in blocks]),n,g))
        self.check('code_block_segmentation',seg)
        self.check('code_block_desegmentation',deseg)

    def test_concatenation(self):
        concat, deconcat = [], []
        for _ in range(self.count):
            lengths = self.rng.integers(0,200,int(self.rng.integers(1,10)))
            blocks = [self.rng.normal(size=n) for n in lengths]
            concat.append((cell(blocks),))
            deconcat.append((np.concatenate(blocks),lengths))
        self.check('code_block_concatenation',concat)
        self.check('code_block_deconcatenation',deconcat)

    def test_interleavers(self):
        # Exhaust every one of the 188 standardized QPP lengths.
        self.check('internal_interleaver',[(self.rng.permutation(k),) for k in QPP])
        self.check('subblock_interleaver',[(self.rng.normal(size=n),i) for i in range(3)
                    for n in [0,1,31,32,33,6148]+self.rng.integers(1,6149,self.count).tolist()])

    def test_rate_matching(self):
        circ, rate = [], []
        for i in range(self.count*2):
            k = int(self.rng.choice(list(QPP)))
            d = self.rng.integers(0,2,(3,k+4)).astype(float)
            d[:2,:int(self.rng.integers(0,min(k,64)))] = np.nan
            v = np.array([t.subblock_interleaver(d[j],j) for j in range(3)])
            params = (int(self.rng.integers(v.shape[1],v.size+1)),i%2,i%4,
                      int(self.rng.choice([0,1,k,3*k,8*k])))
            rate.append((d,*params)); circ.append((v,*params))
        self.check('circular_buffer',circ)
        self.check('rate_matching',rate)

    def test_encoders(self):
        self.check('constituent_encoder',[(self.rng.integers(0,2,n),) for n in
                    [0,1,2,3,40,6144]+self.rng.integers(1,6145,self.count).tolist()],2)
        cases = []
        for k in [40,48,512,1024,2048,6144]+self.rng.choice(list(QPP),self.count).tolist():
            c = self.rng.integers(0,2,k).astype(float)
            c[:int(self.rng.integers(0,min(k,32)))] = np.nan
            cases.append((c,t.internal_interleaver(np.arange(k))))
        self.check('turbo_encoder',cases)

    def test_maxstar(self):
        for approx in [False, True]:
            cases = [(self.rng.normal(size=(n,m))*100,) for n,m in [(1,1),(1,8),(8,1),(8,40)]]
            cases += [(self.rng.normal(size=(8,40))*20,) for _ in range(self.count)]
            cases += [(np.array([[-np.inf,np.inf,0],[-np.inf,np.inf,-np.inf]]),)]
            cases += [(self.rng.normal(size=30)*10,self.rng.normal(size=30)*10) for _ in range(self.count)]
            cases += [(np.array([-np.inf,np.inf,0]),np.array([-np.inf,np.inf,-np.inf]))]
            self.check('maxstar',cases,approximate=approx)

    def test_decoders(self):
        for approx in [False,True]:
            cases = [(self.rng.normal(size=n)*scale,self.rng.normal(size=n)*scale)
                     for n,scale in [(3,0),(4,1),(43,20),(131,100),(6147,1)]]
            cases += [(self.rng.normal(size=n)*4,self.rng.normal(size=n)*4)
                      for n in self.rng.integers(4,200,self.count)]
            x,z = cases[2][0].copy(),cases[2][1].copy(); x[:5]=np.inf; z[:5]=np.inf
            cases.append((x,z))
            self.check('constituent_decoder',cases,approximate=approx)
            dec = []
            for i in range(self.count):
                k = int(self.rng.choice([40,48,64,128,256]))
                pi = t.internal_interleaver(np.arange(k))
                c = self.rng.integers(0,2,k).astype(float)
                c[:i%8] = np.nan
                d = (1-2*t.turbo_encoder(c,pi))*self.rng.uniform(.1,8)+self.rng.normal(size=(3,k+4))*2
                it = [0,.5,1,1.5,2,3,8][i%7]
                dec.append((d,pi,it))
                g = t.get_crc_generator_matrix(k,t.get_3gpp_crc_polynomial('CRC24A'))
                dec.append((d,pi,it,g))
            # Valid CRC, early stop and maximum supported block size.
            for k in [40,6144]:
                g = t.get_crc_generator_matrix(k,t.get_3gpp_crc_polynomial('CRC24A'))
                c = t.generate_and_append_crc_bits(self.rng.integers(0,2,k-24),g)
                pi = t.internal_interleaver(np.arange(k))
                dec.append(((1-2*t.turbo_encoder(c,pi))*8,pi,1,g))
            dec.append((np.zeros((3,44)),t.internal_interleaver(np.arange(40)),8,
                        t.get_crc_generator_matrix(40,t.get_3gpp_crc_polynomial('CRC24A'))))
            self.check('turbo_decoder',dec,2,approx)

    def test_zz_every_numerical_function_has_differential_coverage(self):
        expected = {name for name,f in inspect.getmembers(core,inspect.isfunction) if f.__module__ == core.__name__}
        self.assertEqual(expected,self.covered)


class ChainTests(ComparisonMixin, unittest.TestCase):
    # Inherit comparison helpers only; numerical tests already run above.
    @classmethod
    def setUpClass(cls):
        cls.oracle = Oracle()
        cls.rng = np.random.default_rng(int(os.environ.get('FUZZ_SEED','20260909'))+1)
        cls.count = int(os.environ.get('FUZZ_CASES','16'))

    @classmethod
    def tearDownClass(cls):
        cls.oracle.directory.cleanup()

    def test_chain_properties_and_encoding(self):
        properties = ['CRC_polynomial_TB','CRC_polynomial_CB','L_TB','L_CB','B','C','B_prime',
                      'K_r','F_r','D_r','E_r','N_ref','CRC_generator_matrix_TB',
                      'CRC_generator_matrix_CB','internal_interleaver_patterns','rate_matching_patterns']
        cases = [16,17,40,488,1001,2024,6120,6121,12217]
        cases += self.rng.integers(1,18000,self.count).tolist()
        for i,A in enumerate(cases):
            with self.subTest(A=A):
                C = len(t.get_3gpp_code_block_segment_lengths(A+24))
                Q = [1,2,4,6,8,10][i%6]
                G = int(np.ceil((A*3)/(C*Q))*C*Q)
                config = dict(A=A,G=G,Q_m=Q,N_L=1,rv_idx=i%4,I_LBRM=i%2,N_IR=24000)
                a = self.rng.integers(0,2,A)
                enc = t.turbo_encoding_chain(**config)
                f = enc(a)
                args = ','.join(f"'{k}',{v}" for k,v in config.items())
                script = f'o=turbo_encoding_chain({args}); o.setupImpl(); f=o.stepImpl(a);\n'
                script += '\n'.join(f'p{i}=o.{p};' for i,p in enumerate(properties))
                refs = self.oracle.run(script,{'a':a},['f']+[f'p{i}' for i in range(len(properties))])
                self.compare(f,refs[0])
                for p,ref in zip(properties,refs[1:]):
                    self.compare(getattr(enc,p),ref)

    def test_chain_decoding_harq_tuning_reset_release(self):
        for i in range(max(8,self.count)):
            A = [16,17,40,128,6121][i%5]
            C = len(t.get_3gpp_code_block_segment_lengths(A+24))
            G = int(np.ceil(3*(A+24)/C)*C)
            config = dict(A=A,G=G,I_HARQ=i%2,iterations=[0,.5,1,1.5][i%4])
            enc = t.turbo_encoding_chain(A=A,G=G)
            dec = t.turbo_decoding_chain(**config)
            a = self.rng.integers(0,2,A)
            llrs = []
            py = []
            for rv in [0,2,3]:
                enc.rv_idx = dec.rv_idx = rv
                llr = (1-2*enc(a))*3+self.rng.normal(size=G)*2
                llrs.append(llr)
                ahat,it = dec(llr)
                py.extend([ahat,it,[b.copy() for b in dec.buffers]])
            dec.reset()
            py.append([b.copy() for b in dec.buffers])
            py.extend(dec(llrs[-1]))
            dec.release()
            py.extend(dec(llrs[-1]))
            args = ','.join(f"'{k}',{v}" for k,v in config.items())
            script = f'o=turbo_decoding_chain({args}); o.setupImpl(); result=cell(1,14);\n'
            for j,rv in enumerate([0,2,3]):
                script += f'o.rv_idx={rv}; o.processTunedPropertiesImpl(); [aa,ii]=o.stepImpl(llrs{{{j+1}}}); result{{{3*j+1}}}=aa; result{{{3*j+2}}}=ii; result{{{3*j+3}}}=o.buffers;\n'
            script += 'o.resetImpl(); result{10}=o.buffers; [result{11},result{12}]=o.stepImpl(llrs{3}); o.setupImpl(); [result{13},result{14}]=o.stepImpl(llrs{3});'
            refs = self.oracle.run(script,{'llrs':cell(llrs)},['result'])[0]
            self.compare(py,refs)

    def test_property_validation_and_lifecycle(self):
        for name,value in [('A',-1),('N_IR',-1),('G',-1),('rv_idx',4),('N_L',0),('Q_m',3)]:
            with self.subTest(name=name),self.assertRaises(ValueError):
                t.turbo_coding_chain(**{name:value})
        with self.assertRaises(TypeError):
            t.turbo_coding_chain(unknown=1)
        enc = t.turbo_encoding_chain()
        enc.reset()
        first = enc.step(np.zeros(16))
        enc.reset()
        np.testing.assert_array_equal(first,enc(np.zeros(16)))
        with self.assertRaises(ValueError):
            enc.A = 40
        enc.G = 200
        self.assertEqual(len(enc(np.zeros(16))),200)
        enc.release(); enc.A=40
        self.assertEqual(len(enc(np.zeros(40))),200)

    def test_noiseless_roundtrip(self):
        for A in [16,17,40,1000,6121,12217]:
            with self.subTest(A=A):
                C = len(t.get_3gpp_code_block_segment_lengths(A+24))
                G = int(np.ceil(4*(A+24)/C)*C)
                enc = t.turbo_encoding_chain(A=A,G=G)
                dec = t.turbo_decoding_chain(A=A,G=G,iterations=2)
                a = self.rng.integers(0,2,A)
                ahat,it = dec((1-2*enc(a))*10)
                np.testing.assert_array_equal(a,ahat)
                self.assertTrue(np.all(it <= 2))

    def test_layer_modulation_tuning(self):
        enc = t.turbo_encoding_chain(A=40,G=240)
        a = self.rng.integers(0,2,40)
        enc(a)
        enc.N_L = 2
        enc.Q_m = 6
        f = enc(a)
        refs = self.oracle.run("o=turbo_encoding_chain('A',40,'G',240); o.setupImpl(); o.stepImpl(a); o.N_L=2; o.Q_m=6; o.processTunedPropertiesImpl(); f=o.stepImpl(a);",{'a':a},['f'])
        self.compare(f,refs[0])


class ValidationTests(unittest.TestCase):
    def test_rejected_inputs(self):
        cases = [
            (t.get_3gpp_crc_polynomial,('CRC32',)),
            (t.get_crc_generator_matrix,(3,[1])),
            (t.get_3gpp_code_block_segment_lengths,(0,)),
            (t.internal_interleaver,(np.zeros(41),)),
            (t.subblock_interleaver,(np.zeros(40),3)),
            (t.code_block_deconcatenation,(np.zeros(4),[2,3])),
            (t.turbo_encoder,(np.zeros(40),np.arange(39))),
            (t.turbo_decoder,(np.zeros((2,44)),np.arange(40),1)),
            (t.turbo_decoder,(np.zeros((3,44)),np.arange(39),1)),
            (t.turbo_decoder,(np.zeros((3,44)),np.arange(40),.3)),
            (t.constituent_decoder,(np.zeros(4),np.zeros(5))),
            (t.circular_buffer,(np.zeros((2,32)),96,0,0,4)),
            (t.circular_buffer,(np.zeros((3,31)),96,0,0,4)),
            (t.circular_buffer,(np.zeros((3,32)),96,0,4,4)),
            (t.circular_buffer,(np.full((3,32),np.nan),96,0,0,4)),
        ]
        for function,args in cases:
            with self.subTest(function=function.__name__,args=str(args)[:80]),self.assertRaises(ValueError):
                function(*args)

    def test_every_matlab_entry_point_is_exported(self):
        from oracle import MATLAB
        for source in MATLAB.glob('*.m'):
            self.assertTrue(callable(getattr(t,source.stem,None)),source.stem)
