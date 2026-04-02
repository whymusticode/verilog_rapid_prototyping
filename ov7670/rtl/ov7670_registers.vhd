library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity OV7670_registers is
    Port ( clk      : in  STD_LOGIC;
           advance  : in  STD_LOGIC;
           command  : out STD_LOGIC_VECTOR(15 downto 0);
           finished : out STD_LOGIC);
end OV7670_registers;

architecture Behavioral of OV7670_registers is
    signal sreg   : std_logic_vector(15 downto 0);
    signal address : unsigned(7 downto 0) := (others => '0');
begin
    command  <= sreg;
    finished <= '1' when sreg = x"FFFF" else '0';

    process(clk)
    begin
        if rising_edge(clk) then
            if advance = '1' then
                address <= address + 1;
            end if;

            case address is
                when x"00" => sreg <= x"1280"; -- COM7   Reset
                when x"01" => sreg <= x"1280"; -- COM7   Reset
                when x"02" => sreg <= x"1204"; -- COM7   Set RGB output
                when x"03" => sreg <= x"1100"; -- CLKRC  Internal clock prescaler
                when x"04" => sreg <= x"0C00"; -- COM3   default
                when x"05" => sreg <= x"3E00"; -- COM14  no scaling, normal pclk
                when x"06" => sreg <= x"8C00"; -- RGB444 disable
                when x"07" => sreg <= x"0400"; -- COM1   disable CCIR656
                when x"08" => sreg <= x"40D0"; -- COM15  RGB565, full range
                when x"09" => sreg <= x"3A04"; -- TSLB   UV normal, auto output window
                when x"0A" => sreg <= x"1418"; -- COM9   4x gain ceiling
                when x"0B" => sreg <= x"4FB3"; -- MTX1
                when x"0C" => sreg <= x"50B3"; -- MTX2
                when x"0D" => sreg <= x"5100"; -- MTX3
                when x"0E" => sreg <= x"523D"; -- MTX4
                when x"0F" => sreg <= x"53A7"; -- MTX5
                when x"10" => sreg <= x"54E4"; -- MTX6
                when x"11" => sreg <= x"589E"; -- MTXS
                when x"12" => sreg <= x"3DC0"; -- COM13  gamma enable, UV auto adjust
                when x"13" => sreg <= x"1714"; -- HSTART HREF start high 8 bits
                when x"14" => sreg <= x"1802"; -- HSTOP  HREF stop high 8 bits
                when x"15" => sreg <= x"3280"; -- HREF   edge offset
                when x"16" => sreg <= x"1903"; -- VSTART VSYNC start high 8 bits
                when x"17" => sreg <= x"1A7B"; -- VSTOP  VSYNC stop high 8 bits
                when x"18" => sreg <= x"030A"; -- VREF   VSYNC low bits
                when x"19" => sreg <= x"0F41"; -- COM6   disable HREF at optical black
                when x"1A" => sreg <= x"1E07"; -- MVFP   normal orientation
                when x"1B" => sreg <= x"3340"; -- CHLF
                when x"1C" => sreg <= x"3C78"; -- COM12
                when x"1D" => sreg <= x"6900"; -- GFIX
                when x"1E" => sreg <= x"7400"; -- REG74
                when x"1F" => sreg <= x"B084"; -- RSVD B0
                when x"20" => sreg <= x"B10C"; -- ABLC1
                when x"21" => sreg <= x"B20E"; -- RSVD B2
                when x"22" => sreg <= x"B382"; -- THL_ST
                when x"23" => sreg <= x"7A20"; -- SLOP
                when x"24" => sreg <= x"7B1C"; -- GAM1
                when x"25" => sreg <= x"7C28"; -- GAM2
                when x"26" => sreg <= x"7D3C"; -- GAM3
                when x"27" => sreg <= x"7E55"; -- GAM4
                when x"28" => sreg <= x"7F68"; -- GAM5
                when x"29" => sreg <= x"8076"; -- GAM6
                when x"2A" => sreg <= x"8180"; -- GAM7
                when x"2B" => sreg <= x"8288"; -- GAM8
                when x"2C" => sreg <= x"838F"; -- GAM9
                when x"2D" => sreg <= x"8496"; -- GAM10
                when x"2E" => sreg <= x"85A3"; -- GAM11
                when x"2F" => sreg <= x"86AF"; -- GAM12
                when x"30" => sreg <= x"87C4"; -- GAM13
                when x"31" => sreg <= x"88D7"; -- GAM14
                when x"32" => sreg <= x"89E8"; -- GAM15
                when x"33" => sreg <= x"13E0"; -- COM8   all AGC/AEC/AWB off
                when x"34" => sreg <= x"0000"; -- GAIN
                when x"35" => sreg <= x"1000"; -- AECH
                when x"36" => sreg <= x"0D40"; -- COM4
                when x"37" => sreg <= x"1418"; -- COM9  4x gain
                when x"38" => sreg <= x"A505"; -- BD50MAX
                when x"39" => sreg <= x"AB07"; -- BD60MAX
                when x"3A" => sreg <= x"2475"; -- AEW
                when x"3B" => sreg <= x"2563"; -- AEB
                when x"3C" => sreg <= x"26D4"; -- VPT
                when x"3D" => sreg <= x"9F78"; -- HAECC1
                when x"3E" => sreg <= x"A068"; -- HAECC2
                when x"3F" => sreg <= x"A103"; -- RSVD
                when x"40" => sreg <= x"A6D8"; -- HAECC3
                when x"41" => sreg <= x"A7D8"; -- HAECC4
                when x"42" => sreg <= x"A8F0"; -- HAECC5
                when x"43" => sreg <= x"A990"; -- HAECC6
                when x"44" => sreg <= x"AA94"; -- HAECC7
                when x"45" => sreg <= x"13E5"; -- COM8  AGC/AEC enable
                when others => sreg <= x"FFFF";
            end case;
        end if;
    end process;

end Behavioral;
