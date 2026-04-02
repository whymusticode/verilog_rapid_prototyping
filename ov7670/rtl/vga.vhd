library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity VGA is
    Port ( CLK25       : in  STD_LOGIC;
           rez_160x120 : in  STD_LOGIC;
           rez_320x240 : in  STD_LOGIC;
           Hsync       : out STD_LOGIC;
           Vsync       : out STD_LOGIC;
           Nblank      : out STD_LOGIC;
           clkout      : out STD_LOGIC;
           activeArea  : out STD_LOGIC;
           Nsync       : out STD_LOGIC);
end VGA;

architecture Behavioral of VGA is
    signal hcount : unsigned(9 downto 0) := (others => '0');
    signal vcount : unsigned(9 downto 0) := (others => '0');
    signal hactive, vactive : std_logic;
begin
    clkout <= CLK25;
    Nsync  <= '1';

    process(CLK25)
    begin
        if rising_edge(CLK25) then
            if hcount = 799 then
                hcount <= (others => '0');
                if vcount = 524 then
                    vcount <= (others => '0');
                else
                    vcount <= vcount + 1;
                end if;
            else
                hcount <= hcount + 1;
            end if;
        end if;
    end process;

    -- 640x480 @ 60Hz standard VGA timing
    Hsync <= '0' when (hcount >= 656 and hcount < 752) else '1';
    Vsync <= '0' when (vcount >= 490 and vcount < 492) else '1';

    hactive <= '1' when hcount < 640 else '0';
    vactive <= '1' when vcount < 480 else '0';

    activeArea <= hactive and vactive;
    Nblank     <= hactive and vactive;

end Behavioral;
