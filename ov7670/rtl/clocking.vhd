library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
library UNISIM;
use UNISIM.VComponents.all;

entity clocking is
    Port ( CLK_100 : in  STD_LOGIC;
           CLK_50  : out STD_LOGIC;
           CLK_25  : out STD_LOGIC);
end clocking;

architecture Behavioral of clocking is
    signal clkfb   : std_logic;
    signal clk50_i : std_logic;
    signal clk25_i : std_logic;
begin

    MMCME2_inst : MMCME2_BASE
    generic map (
        CLKFBOUT_MULT_F  => 10.0,    -- 100 * 10 = 1000 MHz VCO
        CLKIN1_PERIOD    => 10.0,     -- 100 MHz input
        CLKOUT0_DIVIDE_F => 20.0,    -- 1000 / 20 = 50 MHz
        CLKOUT1_DIVIDE   => 40       -- 1000 / 40 = 25 MHz
    )
    port map (
        CLKIN1   => CLK_100,
        CLKFBIN  => clkfb,
        CLKFBOUT => clkfb,
        CLKOUT0  => clk50_i,
        CLKOUT1  => clk25_i,
        CLKOUT2  => open,
        CLKOUT3  => open,
        CLKOUT4  => open,
        CLKOUT5  => open,
        CLKOUT6  => open,
        CLKOUT0B => open,
        CLKOUT1B => open,
        CLKOUT2B => open,
        CLKOUT3B => open,
        LOCKED   => open,
        PWRDWN   => '0',
        RST      => '0'
    );

    buf50 : BUFG port map (I => clk50_i, O => CLK_50);
    buf25 : BUFG port map (I => clk25_i, O => CLK_25);

end Behavioral;
