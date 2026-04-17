function [acm, V] = matrix_eig_10_fxp(acm, V)
% One Jacobi iteration, fixed-point (GNU Octave fi; pkg load fixedpoint), target XCZU7EV.
% I/O: 23-bit integer complex (46 bit total). Internal 32,8 for matrix; 3-mult (preadder) for complex mult.
  n = 10;
  WL_IO = 23;
  FL_IO = 0;
  WL = 32;
  FL = 8;
  WL_angle = 18;
  FL_angle = 16;
  F = fimath('OverflowAction', 'Wrap', 'RoundingMethod', 'Floor');

  % Cycle bounds: find_max=1, divide=FL bits, cordic_theta=16, cordic_phi=16, sincos=1, apply=1
  S1_END = 1;
  S2_END = S1_END + FL;
  S3_END = S2_END + 16;
  S4_END = S3_END + 16;
  S5_END = S4_END + 1;
  N_CYCLES = S5_END + 1;

  off_diag_max = fi(0, 1, WL, FL, F);
  p = 1; q = 2;
  a_pp = fi(0, 1, WL, FL, F);
  a_qq = fi(0, 1, WL, FL, F);
  a_pq_re = fi(0, 1, WL, FL, F);
  a_pq_im = fi(0, 1, WL, FL, F);
  numer = fi(0, 1, WL, FL, F);
  denom = fi(0, 1, WL, FL, F);
  ratio = fi(0, 1, WL, FL, F);
  theta = fi(0, 1, WL_angle, FL_angle, F);
  phi = fi(0, 1, WL_angle, FL_angle, F);
  cos_theta = fi(0, 1, WL_angle, FL_angle, F);
  sin_theta = fi(0, 1, WL_angle, FL_angle, F);
  cos_phi = fi(0, 1, WL_angle, FL_angle, F);
  sin_phi = fi(0, 1, WL_angle, FL_angle, F);
  rem_div = fi(0, 1, WL, FL, F);
  quot_div = fi(0, 1, WL, FL, F);
  skip_theta_cordic = false;
  x_theta = fi(0, 1, WL+4, FL, F);
  y_theta = fi(0, 1, WL+4, FL, F);
  z_theta = fi(0, 1, WL_angle+4, FL_angle, F);
  x_phi = fi(0, 1, WL+4, FL, F);
  y_phi = fi(0, 1, WL+4, FL, F);
  z_phi = fi(0, 1, WL_angle+4, FL_angle, F);

  % Cast 23-bit integer I/O to internal 32,8 (scale up by 2^FL). Use double at boundary to avoid Octave bool_value on fi.
  scale_up_fi = fi(2^FL, 1, WL, 0, F);
  acm_re = double(real(acm)); acm_im = double(imag(acm));
  V_re = double(real(V)); V_im = double(imag(V));
  scale = double(scale_up_fi);
  acm_fi = fi(complex(acm_re * scale, acm_im * scale), 1, WL, FL, F);
  V_fi = fi(complex(V_re * scale, V_im * scale), 1, WL, FL, F);

  for clock_edge = 1 : N_CYCLES
    if clock_edge <= S1_END
      % State 1: FIND_MAX
      off_diag_max = fi(0, 1, WL, FL, F);
      p = 1; q = 2;
      for i = 1 : n
        for j = (i+1) : n
          aij_re = real(acm_fi(i,j));
          aij_im = imag(acm_fi(i,j));
          mag_sq = fi(aij_re * aij_re + aij_im * aij_im, 1, WL, FL, F);
          mag = sqrt_fi(mag_sq, WL, FL, F);
          if double(storedInteger(mag)) > double(storedInteger(off_diag_max))
            off_diag_max = mag;
            p = i; q = j;
          end
        end
      end
      a_pp = real(acm_fi(p,p));
      a_qq = real(acm_fi(q,q));
      a_pq_re = real(acm_fi(p,q));
      a_pq_im = imag(acm_fi(p,q));
      numer = fi(fi(2, 1, WL, FL, F) * off_diag_max, 1, WL, FL, F);
      denom = fi(a_pp - a_qq, 1, WL, FL, F);
      rem_div = numer;
      quot_div = fi(0, 1, WL, FL, F);
    elseif clock_edge <= S2_END
      % State 2: DIVIDE one bit per clock (iterative; denom=0 -> ratio=0)
      step = clock_edge - S1_END - 1;
      si = double(storedInteger(denom));
      den_abs = fi(abs(si) * 2^-FL, 0, WL, FL, F);
      if double(storedInteger(den_abs)) == 0
        ratio = fi(0, 1, WL, FL, F);
        theta = fi(pi/4, 1, WL_angle, FL_angle, F);
        skip_theta_cordic = true;
      else
        [rem_div, quot_div] = fxp_divide_one_bit(rem_div, quot_div, den_abs, step, WL, FL, F);
        if step == FL - 1
          if (double(storedInteger(numer)) < 0) ~= (double(storedInteger(denom)) < 0)
            ratio = fi(-quot_div, 1, WL, FL, F);
          else
            ratio = quot_div;
          end
        end
      end
      if step == 0
        x_theta = fi(denom, 1, WL+4, FL, F);
        y_theta = fi(numer, 1, WL+4, FL, F);
        z_theta = fi(0, 1, WL_angle+4, FL_angle, F);
      end
    elseif clock_edge <= S3_END
      % State 3: CORDIC atan(numer/denom) -> theta (vectoring on (denom, numer))
      step = clock_edge - S2_END - 1;
      [x_theta, y_theta, z_theta] = cordic_vectoring_step(x_theta, y_theta, z_theta, step, WL, FL, WL_angle, FL_angle, F);
      if step == 15
        if ~skip_theta_cordic
          theta = fi(bitsra(z_theta, 1), 1, WL_angle, FL_angle, F);
        end
      end
    elseif clock_edge <= S4_END
      % State 4: CORDIC atan2(a_pq_re, a_pq_im) -> phi = -angle(a_pq)
      step = clock_edge - S3_END - 1;
      if step == 0
        x_phi = fi(a_pq_re, 1, WL+4, FL, F);
        y_phi = fi(a_pq_im, 1, WL+4, FL, F);
        z_phi = fi(0, 1, WL_angle+4, FL_angle, F);
      end
      if step <= 15
        [x_phi, y_phi, z_phi] = cordic_vectoring_step(x_phi, y_phi, z_phi, step, WL, FL, WL_angle, FL_angle, F);
      end
      if step == 15
        phi = fi(-z_phi, 1, WL_angle, FL_angle, F);
      end
    elseif clock_edge <= S5_END
      % State 5: Sin/cos LUT for theta and phi
      [cos_theta, sin_theta] = sin_cos_lut_fxp(theta, WL_angle, FL_angle, F);
      [cos_phi, sin_phi] = sin_cos_lut_fxp(phi, WL_angle, FL_angle, F);
    else
      % State 6: Apply U
      [acm_fi, V_fi] = apply_jacobi_rotation_fxp(acm_fi, V_fi, p, q, cos_theta, sin_theta, cos_phi, sin_phi, n, WL, FL, WL_angle, FL_angle, F);
    end
  end

  % Cast back to 23-bit integer: round and scale down by 2^FL (bitsra with rounding)
  half = fi(2^(FL-1), 1, WL, 0, F);
  acm_re = fi(bitsra(real(acm_fi) + half, FL), 1, WL_IO, FL_IO, F);
  acm_im = fi(bitsra(imag(acm_fi) + half, FL), 1, WL_IO, FL_IO, F);
  acm = fi(complex(acm_re, acm_im), 1, WL_IO, FL_IO, F);
  V_re = fi(bitsra(real(V_fi) + half, FL), 1, WL_IO, FL_IO, F);
  V_im = fi(bitsra(imag(V_fi) + half, FL), 1, WL_IO, FL_IO, F);
  V = fi(complex(V_re, V_im), 1, WL_IO, FL_IO, F);
end

function [rem_next, quot_next] = fxp_divide_one_bit(rem_in, quot_in, den_abs, step, WL, FL, F)
  % One bit of restoring divide: rem holds scaled dividend; quotient built bit by bit.
  rem_shift = fi(rem_in * 2, 1, WL, FL, F);
  if double(storedInteger(rem_shift)) >= double(storedInteger(den_abs))
    rem_next = fi(rem_shift - den_abs, 1, WL, FL, F);
    bit_val_fi = fi(2^(-(step + 1)), 1, WL, FL, F);
    quot_next = quot_in + bit_val_fi;
  else
    rem_next = fi(rem_shift, 1, WL, FL, F);
    quot_next = quot_in;
  end
end

function q = fxp_divide_full(num, den, WL, FL, F)
  si = double(storedInteger(den));
  den_abs = fi(abs(si) * 2^-FL, 0, WL, FL, F);
  if double(storedInteger(den_abs)) == 0
    q = fi(0, 1, WL, FL, F);
    return
  end
  rem_div = num;
  quot_div = fi(0, 1, WL, FL, F);
  for step = 0 : FL-1
    [rem_div, quot_div] = fxp_divide_one_bit(rem_div, quot_div, den_abs, step, WL, FL, F);
  end
  if (double(storedInteger(num)) < 0) ~= (double(storedInteger(den)) < 0)
    q = fi(-quot_div, 1, WL, FL, F);
  else
    q = quot_div;
  end
end

function m = sqrt_fi(mag_sq_fi, WL, FL, F)
  % Newton: x := (x + mag_sq/x)/2, 4 iterations, fi only.
  x = fi(mag_sq_fi, 1, WL, FL, F);
  for ii = 1 : 4
    q = fxp_divide_full(mag_sq_fi, x, WL, FL, F);
    x = bitsra(x + q, 1);
  end
  m = fi(x, 1, WL, FL, F);
end

function [x_n, y_n, z_n] = cordic_vectoring_step(x, y, z, k, WL_xy, FL_xy, WL_z, FL_z, F)
  persistent atan_tbl;
  if isempty(atan_tbl)
    atan_tbl = fi([0.785398163397448; 0.463647609000806; 0.244978663126864; 0.124354994546761; ...
      0.0624188099959574; 0.0312398334302683; 0.0156237286204768; 0.00781234106010111; ...
      0.00390623013196697; 0.00195312251647882; 0.000976562189559320; 0.000488281211194898; ...
      0.000244140620149362; 0.000122070311893670; 0.0000610351561742096; 0.0000305175781155261], ...
      1, WL_z, FL_z, F);
  end
  idx = k + 1;
  x_s = bitsra(x, k);
  y_s = bitsra(y, k);
  if double(storedInteger(y)) >= 0
    x_n = fi(x + y_s, 1, WL_xy+4, FL_xy, F);
    y_n = fi(y - x_s, 1, WL_xy+4, FL_xy, F);
    z_n = fi(z + atan_tbl(idx), 1, WL_z+4, FL_z, F);
  else
    x_n = fi(x - y_s, 1, WL_xy+4, FL_xy, F);
    y_n = fi(y + x_s, 1, WL_xy+4, FL_xy, F);
    z_n = fi(z - atan_tbl(idx), 1, WL_z+4, FL_z, F);
  end
end

function [c, s] = sin_cos_lut_fxp(angle_fi, WL, FL, F)
  persistent lut;
  Q = min(10, FL);
  TABLE_SIZE = 2^Q + 1;
  if isempty(lut)
    lut = fi(zeros(TABLE_SIZE, 1), 1, WL, FL, F);
    for i = 0 : TABLE_SIZE-1
      lut(i+1) = fi(sin((i / 2^Q) * pi/2), 1, WL, FL, F);
    end
  end
  two_over_pi = fi(2/pi, 1, WL, FL, F);
  scaled = fi(angle_fi * two_over_pi, 1, WL, FL, F);
  norm_bits = fi(scaled, 0, Q+2, FL, F);
  norm_int = storedInteger(norm_bits);
  quadrant = bitshift(norm_int, -Q);
  quadrant = bitand(quadrant, 3);
  phase_int = bitand(norm_int, 2^Q - 1);
  if double(bitand(quadrant, 1)) ~= 0
    phase_int = 2^Q - phase_int;
  end
  phase_int = min(max(double(phase_int), 0), TABLE_SIZE - 1);
  lut_val = lut(phase_int + 1);
  if double(quadrant) >= 2
    s = fi(-lut_val, 1, WL, FL, F);
  else
    s = fi(lut_val, 1, WL, FL, F);
  end
  scaled_c = fi(angle_fi * two_over_pi + 1, 1, WL, FL, F);
  norm_c = fi(scaled_c, 0, Q+2, FL, F);
  norm_int_c = storedInteger(norm_c);
  quad_c = bitshift(norm_int_c, -Q);
  quad_c = bitand(quad_c, 3);
  phase_c = bitand(norm_int_c, 2^Q - 1);
  if double(bitand(quad_c, 1)) ~= 0
    phase_c = 2^Q - phase_c;
  end
  phase_c = min(max(double(phase_c), 0), TABLE_SIZE - 1);
  lut_c = lut(phase_c + 1);
  if double(quad_c) >= 2
    c = fi(-lut_c, 1, WL, FL, F);
  else
    c = fi(lut_c, 1, WL, FL, F);
  end
end

function [acm_out, V_out] = apply_jacobi_rotation_fxp(acm_in, V_in, p, q, cth, sth, cph, sph, n, WL, FL, WL_angle, FL_angle, F)
  % U from theta, phi; 3-mult (preadder) for all complex multiplies.
  U = fi(eye(n), 1, WL_angle, FL_angle, F);
  U(p,p) = cth;
  U(p,q) = cmul3_fxp(sth, fi(complex(cph, -sph), 1, WL_angle, FL_angle, F), F);
  U(q,p) = cmul3_fxp(sth, fi(complex(cph, sph), 1, WL_angle, FL_angle, F), F);
  U(q,q) = fi(-cth, 1, WL_angle, FL_angle, F);
  T = matmul_cmul3_fxp(U', acm_in, WL, FL, WL_angle, FL_angle, F);
  acm_out = matmul_cmul3_fxp(T, U, WL, FL, WL_angle, FL_angle, F);
  acm_out(p,q) = 0;
  acm_out(q,p) = 0;
  V_out = matmul_cmul3_fxp(V_in, U, WL, FL, WL_angle, FL_angle, F);
end

function c = cmul3_fxp(a, b, F)
  % Complex multiply with 3 real multiplies (preadder): s1=a_re*b_re, s2=a_im*b_im, s3=(a_re+a_im)*(b_re+b_im); re=s1-s2, im=s3-s1-s2.
  a_re = real(a);
  a_im = imag(a);
  b_re = real(b);
  b_im = imag(b);
  s1 = a_re * b_re;
  s2 = a_im * b_im;
  s3 = (a_re + a_im) * (b_re + b_im);
  c_re = s1 - s2;
  c_im = s3 - s1 - s2;
  wl = max(c_re.WordLength, c_im.WordLength);
  fl = max(c_re.FractionLength, c_im.FractionLength);
  c_re_q = fi(c_re, 1, wl, fl, F);
  c_im_q = fi(c_im, 1, wl, fl, F);
  c = fi(complex(c_re_q, c_im_q), 1, wl, fl, F);
end

function C = matmul_cmul3_fxp(A, B, WL, FL, WL_angle, FL_angle, F)
  [ra, ca] = size(A);
  [~, cb] = size(B);
  C = fi(complex(zeros(ra, cb), zeros(ra, cb)), 1, WL, FL, F);
  for i = 1 : ra
    for j = 1 : cb
      s = fi(complex(0, 0), 1, WL + WL_angle + 6, FL + FL_angle, F);
      for k = 1 : ca
        p = cmul3_fxp(A(i,k), B(k,j), F);
        s = s + p;
      end
      C(i,j) = fi(s, 1, WL, FL, F);
    end
  end
end
