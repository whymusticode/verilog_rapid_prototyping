% Compare float vs fxp, 23-bit integer I/O. Fixed scale: acm = vect*vect' / 2^ACM_SCALE.
% With BW=14, M=100: max |acm| <= M*2^(2*BW)/2^ACM_SCALE = 100*2^28/2^28 = 100, fits in 23 bits.
% Octave fixedpoint: double(complex fi) returns only real; use real+1i*imag for full complex.
pkg load fixedpoint  % we're using Octave
debug_on_error(1);  % on error: at debug prompt run dbstack to see failing line
rng(0);
N = 10;
BW = 14;
M = 100;
max_iter = 1;
Nmonte = 1;
tol = 1e-8;
WL_IO = 23;
ACM_SCALE = 14;  

for l = 1:Nmonte
    vect = randi([-2^BW, 2^BW-1], N, M) + 1i * randi([-2^BW, 2^BW-1], N, M);
    acm_dbl = vect * vect' / 2^ACM_SCALE;
    [~, D] = eig(acm_dbl);
    true_eig = diag(D);

    % Float path
    acm_fl = acm_dbl;
    V_fl = eye(N);
    % Fxp path: 23-bit integer, fixed scale (no clamp)
    acm_fx = fi(round(acm_dbl), 1, WL_IO, 0, fimath('OverflowAction', 'Wrap', 'RoundingMethod', 'Floor'));
    V_fx = fi(eye(N), 1, WL_IO, 0, fimath('OverflowAction', 'Wrap', 'RoundingMethod', 'Floor'));

    for k = 1:max_iter
        [acm_fl, V_fl] = matrix_eig_10(acm_fl, V_fl);
        [acm_fx, V_fx] = matrix_eig_10_fxp(acm_fx, V_fx);
        disp(acm_fl)
        acm_fx_dbl = double(real(acm_fx)) + 1i*double(imag(acm_fx));
        disp(acm_fx_dbl)

        off_diag_fl = 0;
        for i = 1:N
            for j = (i+1):N
                off_diag_fl = max(off_diag_fl, abs(acm_fl(i,j)));
            end
        end
        if off_diag_fl < tol
            break
        end

        % Divergence per iteration: eigenvalues and off-diagonal (use acm_fx_dbl for complex)
        eig_fl = diag(acm_fl);
        eig_fx = diag(acm_fx_dbl);
        [~, ord_true] = sort(real(true_eig));
        [~, ord_fl] = sort(real(eig_fl));
        [~, ord_fx] = sort(real(eig_fx));
        err_eig_fl = max(abs(true_eig(ord_true) - eig_fl(ord_fl)));
        err_eig_fx = max(abs(true_eig(ord_true) - eig_fx(ord_fx)));
        off_diag_fx = 0;
        for i = 1:N
            for j = (i+1):N
                off_diag_fx = max(off_diag_fx, abs(acm_fx_dbl(i,j)));
            end
        end
        fprintf('iter %d: float off_diag=%.2e eig_err=%.2e | fxp off_diag=%.2e eig_err=%.2e\n', ...
            k, off_diag_fl, err_eig_fl, off_diag_fx, err_eig_fx);
    end
    fprintf('---\n');
end
