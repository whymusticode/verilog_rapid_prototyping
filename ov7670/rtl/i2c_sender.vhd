library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity i2c_sender is
    Port ( clk   : in    STD_LOGIC;
           send  : in    STD_LOGIC;
           taken : out   STD_LOGIC;
           id    : in    STD_LOGIC_VECTOR(7 downto 0);
           reg   : in    STD_LOGIC_VECTOR(7 downto 0);
           value : in    STD_LOGIC_VECTOR(7 downto 0);
           siod  : inout STD_LOGIC;
           sioc  : out   STD_LOGIC);
end i2c_sender;

architecture Behavioral of i2c_sender is
    signal divider   : unsigned(7 downto 0) := (others => '0');
    signal busy_sr   : std_logic_vector(31 downto 0) := (others => '0');
    signal data_sr   : std_logic_vector(31 downto 0) := (others => '1');
begin

    taken <= '1' when busy_sr(31) = '0' and send = '1' else '0';

    process(busy_sr, data_sr(31))
    begin
        if busy_sr(31) = '0' then
            siod <= 'Z';
        else
            siod <= data_sr(31);
        end if;
    end process;

    process(clk)
    begin
        if rising_edge(clk) then
            if busy_sr(31) = '0' then
                sioc <= '1';
                if send = '1' then
                    -- Start condition, then ID, reg, value with ACK bits
                    data_sr <= "1111" & id & '0' & reg & '0' & value & '0' & '0';
                    busy_sr <= "1111111111111111111111111111111" & '0';
                    divider <= (others => '0');
                end if;
            else
                if divider = x"00" then
                    sioc <= '0';
                elsif divider = x"40" then
                    -- data changes in middle of low
                    busy_sr <= busy_sr(30 downto 0) & '0';
                    data_sr <= data_sr(30 downto 0) & '1';
                elsif divider = x"80" then
                    sioc <= '1';
                end if;
                divider <= divider + 1;
            end if;
        end if;
    end process;

end Behavioral;
