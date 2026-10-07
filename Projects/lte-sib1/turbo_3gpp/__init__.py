"""Independent Python implementation of turbo-3gpp-matlab."""
from .core import (calculate_crc_bits, check_and_remove_crc_bits, circular_buffer,
    code_block_concatenation, code_block_deconcatenation, code_block_desegmentation,
    code_block_segmentation, constituent_decoder, constituent_encoder,
    generate_and_append_crc_bits, get_3gpp_code_block_segment_lengths,
    get_3gpp_crc_polynomial, get_3gpp_encoded_code_block_segment_lengths,
    get_crc_generator_matrix, internal_interleaver, maxstar, rate_matching,
    subblock_interleaver, turbo_decoder, turbo_encoder)
from .chains import turbo_coding_chain, turbo_encoding_chain, turbo_decoding_chain
from .simulation import plot_BLER_vs_SNR, plot_SNR_vs_A
