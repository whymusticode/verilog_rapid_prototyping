function [acm,V] = matrix_eig_10(acm,V)
% One Jacobi iteration. Call repeatedly until converged.
n = size(acm, 1);
off_diag_max = 0;
p = 1;
q = 2;
for i = 1:n
    for j = (i+1):n
        if abs(acm(i,j)) > off_diag_max
            off_diag_max = abs(acm(i,j));
            p = i;
            q = j;
        end
    end
end
a_pp = acm(p,p);
a_qq = acm(q,q);
a_pq = acm(p,q);
theta = 0.5 * atan((2 * abs(a_pq)) / (a_pp - a_qq));
phi = -angle(a_pq);
U = eye(n);
U(p,p) = cos(theta);
U(p,q) = sin(theta) * exp(-1i * phi);
U(q,p) = sin(theta) * exp(1i * phi);
U(q,q) = -cos(theta);
acm = U' * acm * U;
acm(p,q) = 0;
acm(q,p) = 0;
V = V * U;
end
